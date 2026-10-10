"""
GPU engine: llama.cpp's `llama-server.exe` (CUDA 12 build), run as a child process of the backend.

Why: the llama-cpp-python binding installed for Python 3.14 is CPU-only (Qwen2.5 1.5B at about
15 tokens/s). The CUDA build bundled in backend/llama-bin.zip ran the same model at ~150 tok/s
and the 7B model at ~44 tok/s on the RTX 3050 (Phase 0 probe). Decision D1 in docs/ROADMAP.md.

Safety rules (covered by tests/core/test_llama_sidecar.py):
  * Binaries come only from backend/llama-bin.zip and must match the SHA-256 list in
    backend/llama-bin.sha256.json before every start. A changed or missing file is restored from
    the zip, and each restored file is checked before it is put in place. An unknown .dll/.exe in
    the folder, or a zip whose contents don't match, stops the GPU engine (Sentinel then falls
    back to the CPU model).
  * The server listens on 127.0.0.1 only, on a free port picked per start, and requires a random
    API key made per start. The key reaches the child through its environment (LLAMA_API_KEY),
    never the command line (other programs can read command lines), and is masked in Sentinel's
    own logs.
  * Before Sentinel sends it anything private, it checks that the port belongs to its own child
    process and that the server rejects requests without the key. Otherwise it stops the server.
  * The child gets a minimal environment: no session token or other secrets, and a PATH with only
    the binary folder, the CUDA runtime from the venv and Windows' own folders (no DLL hijacking
    through user folders on PATH).
  * It runs in a Windows Job Object with "kill on job close": if the backend exits or crashes,
    Windows ends llama-server too, so the VRAM is always given back.
  * No model downloads (llama-server's download options are never passed), no verbose logging
    (llama-server.log never holds prompts), below-normal CPU priority.
  * Talking to it is local IPC on loopback, not internet access, so it does not go through the
    egress guard. The HTTP client ignores proxy settings, so prompts can't be routed elsewhere.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

from app.core import redaction
from app.core.gpu_monitor import gpu_monitor, vram_pressure_percent
from app.core.paths import LOGS_DIR

BACKEND_DIR = Path(__file__).resolve().parents[2]
BIN_DIR = BACKEND_DIR / "llama-bin"
ZIP_PATH = BACKEND_DIR / "llama-bin.zip"
MANIFEST_PATH = BACKEND_DIR / "llama-bin.sha256.json"
SERVER_EXE = "llama-server.exe"
CUDA_PACKAGES = ("nvidia.cuda_runtime", "nvidia.cublas")   # cudart64_12.dll, cublas(Lt)64_12.dll

HOST = "127.0.0.1"
START_TIMEOUT_S = 180.0
MIB = 1048576.0
RESERVE_MB = 1024.0          # VRAM that must stay free for the owner's other programs after loading
MAX_PRESSURE_AFTER = 80.0    # stay clear of the governor's 85 % "PC busy" line after loading
_CHUNK = 1 << 20

# Harmless variables the child may see (the CUDA driver keeps its kernel cache under APPDATA).
_ENV_PASSTHROUGH = ("SYSTEMDRIVE", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE",
                    "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS")

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


class SidecarError(RuntimeError):
    """The GPU engine can't be used right now. The message is safe to show: it never holds secrets."""


# ── binaries ──────────────────────────────────────────────────────
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _safe_name(name: str) -> bool:
    return (isinstance(name, str) and name not in ("", ".", "..")
            and not any(c in name for c in "/\\:"))


def load_manifest() -> Dict[str, Any]:
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SidecarError("the binary hash list backend/llama-bin.sha256.json is missing") from None
    except (OSError, ValueError) as e:
        raise SidecarError(f"backend/llama-bin.sha256.json is unreadable ({type(e).__name__})") from None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or SERVER_EXE not in files:
        raise SidecarError("backend/llama-bin.sha256.json does not list llama-server.exe")
    for name, meta in files.items():
        digest = meta.get("sha256") if isinstance(meta, dict) else None
        if not _safe_name(name) or not isinstance(digest, str) or len(digest) != 64:
            raise SidecarError(f"backend/llama-bin.sha256.json has a bad entry: {name!r}")
    return data


def _file_ok(path: Path, meta: Dict[str, Any]) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if meta.get("bytes") is not None and size != int(meta["bytes"]):
        return False
    return _sha256_file(path) == meta["sha256"].lower()


def _extract(manifest: Dict[str, Any], names: List[str]) -> None:
    if not ZIP_PATH.exists():
        raise SidecarError("backend/llama-bin.zip is missing, so changed or missing binaries can't be restored")
    want_zip = str(manifest.get("zip_sha256") or "").lower()
    if want_zip and _sha256_file(ZIP_PATH) != want_zip:
        raise SidecarError("backend/llama-bin.zip does not match its SHA-256; refusing to use it")
    files = manifest["files"]
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for name in names:
            meta = files[name]
            tmp = BIN_DIR / (name + ".partial")
            h = hashlib.sha256()
            try:
                # Read by the name in the hash list and write to BIN_DIR/<plain name>: paths inside
                # the zip can never place files elsewhere.
                with zf.open(str(meta.get("zip_path") or name)) as src, open(tmp, "wb") as dst:
                    for block in iter(lambda: src.read(_CHUNK), b""):
                        h.update(block)
                        dst.write(block)
                if h.hexdigest() != meta["sha256"].lower():
                    raise SidecarError(f"{name} inside backend/llama-bin.zip does not match its SHA-256; refusing to use it")
                os.replace(tmp, BIN_DIR / name)
            except SidecarError:
                raise
            except KeyError:
                raise SidecarError(f"{name} is not inside backend/llama-bin.zip") from None
            except Exception as e:
                raise SidecarError(f"could not restore {name} from backend/llama-bin.zip ({type(e).__name__}); "
                                   "is an old llama-server still running?") from None
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass


_verify_lock = threading.Lock()


def ensure_binaries() -> Path:
    """Check every binary against the hash list, restoring changed or missing ones from the zip.
    Returns the path of llama-server.exe. Raises SidecarError when the set can't be trusted."""
    with _verify_lock:
        manifest = load_manifest()
        files = manifest["files"]
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        known = {n.lower() for n in files}
        unknown = sorted(p.name for p in BIN_DIR.iterdir()
                         if p.is_file() and p.suffix.lower() in (".dll", ".exe") and p.name.lower() not in known)
        if unknown:
            raise SidecarError(f"unexpected program file backend/llama-bin/{unknown[0]}: only files from "
                               "llama-bin.zip may be there (move it away to use the GPU engine)")
        bad = [n for n, meta in files.items() if not _file_ok(BIN_DIR / n, meta)]
        if bad:
            print(f"[GPU engine] Restoring {len(bad)} binary file(s) from llama-bin.zip")
            _extract(manifest, bad)
            still = [n for n in bad if not _file_ok(BIN_DIR / n, files[n])]
            if still:
                raise SidecarError(f"{still[0]} still does not match its SHA-256 after restoring it")
        return BIN_DIR / SERVER_EXE


@lru_cache(maxsize=1)
def cuda_dll_dirs() -> Tuple[Tuple[str, ...], Optional[str]]:
    """Folders holding the CUDA runtime DLLs of the pinned nvidia-* pip packages, or a reason."""
    dirs = []
    for mod in CUDA_PACKAGES:
        try:
            spec = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            spec = None
        found = None
        for loc in (list(spec.submodule_search_locations or []) if spec else []):
            if (Path(loc) / "bin").is_dir():
                found = str(Path(loc) / "bin")
                break
        if found is None:
            pip_name = mod.replace("nvidia.", "nvidia-").replace("_", "-") + "-cu12"
            return (), f"the CUDA runtime package {pip_name} is not installed"
        dirs.append(found)
    return tuple(dirs), None


# ── process ───────────────────────────────────────────────────────
def build_env(api_key: str, cuda_dirs) -> Dict[str, str]:
    """The child's whole environment. Nothing is inherited except harmless system variables:
    no session token, no other secrets, no proxy settings, no stray LLAMA_* options."""
    sysroot = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    env = {k: os.environ[k] for k in _ENV_PASSTHROUGH if os.environ.get(k)}
    env["SYSTEMROOT"] = sysroot
    env["WINDIR"] = sysroot
    env["PATH"] = ";".join([str(BIN_DIR), *cuda_dirs, str(Path(sysroot) / "System32"), sysroot])
    env["LLAMA_API_KEY"] = api_key
    env["LLAMA_ARG_NO_WEBUI"] = "1"     # no browser UI (builds without the option ignore it)
    return env


def build_command(exe: Path, model_path: Path, port: int, n_ctx: int, n_gpu_layers: int) -> List[str]:
    # The API key is deliberately NOT part of the command line.
    return [str(exe), "-m", str(model_path), "--host", HOST, "--port", str(int(port)),
            "-c", str(int(n_ctx)), "-ngl", str(int(n_gpu_layers)), "-np", "1"]


def _creation_flags() -> int:
    # No console window; below-normal CPU priority so the owner's programs come first.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _log_tail(path: Path, lines: int = 12) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log)"
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()][-lines:]
    return redaction.redact(" | ".join(tail))[:1500] or "(empty log)"


@lru_cache(maxsize=1)
def _win32():
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Io(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount",
                                                    "OtherOperationCount", "ReadTransferCount",
                                                    "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return ctypes, k32, Extended


class JobObject:
    """Windows Job Object with KILL_ON_JOB_CLOSE: closing it, or this process ending for any
    reason (even a crash), ends every process inside it."""

    def __init__(self, handle):
        self._handle = handle

    @classmethod
    def for_pid(cls, pid: int) -> Optional["JobObject"]:
        if sys.platform != "win32":
            return None
        ctypes, k32, Extended = _win32()
        job = k32.CreateJobObjectW(None, None)
        if not job:
            raise SidecarError(f"CreateJobObject failed (Windows error {ctypes.get_last_error()})")
        try:
            info = Extended()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                               ctypes.byref(info), ctypes.sizeof(info)):
                raise SidecarError(f"SetInformationJobObject failed (Windows error {ctypes.get_last_error()})")
            proc = k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid))
            if not proc:
                raise SidecarError(f"OpenProcess failed (Windows error {ctypes.get_last_error()})")
            try:
                if not k32.AssignProcessToJobObject(job, proc):
                    raise SidecarError(f"AssignProcessToJobObject failed (Windows error {ctypes.get_last_error()})")
            finally:
                k32.CloseHandle(proc)
        except BaseException:
            k32.CloseHandle(job)
            raise
        return cls(job)

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle:
            _win32()[1].CloseHandle(handle)


def _verify_listener(pid: int, port: int) -> None:
    """The port must be held by our own child and only on loopback, before it gets the key."""
    import psutil
    try:
        p = psutil.Process(pid)
        conns = (getattr(p, "net_connections", None) or p.connections)(kind="inet")
    except Exception as e:
        raise SidecarError(f"could not confirm which program listens on port {port} ({type(e).__name__})") from None
    listening = [c for c in conns if c.status == psutil.CONN_LISTEN and c.laddr]
    if any(c.laddr.ip not in ("127.0.0.1", "::1") for c in listening):
        raise SidecarError("llama-server listens beyond this PC; refusing to use it")
    if not any(c.laddr.port == port for c in listening):
        raise SidecarError(f"port {port} is not held by Sentinel's own llama-server; refusing to send it anything")


def _verify_auth(client: httpx.Client, port: int, key: str) -> None:
    """The server must reject requests without the key and accept ours."""
    url = f"http://{HOST}:{port}/props"
    code = client.get(url, timeout=5.0).status_code
    if code != 401:
        raise SidecarError(f"llama-server answered without the API key (HTTP {code}); refusing to use it")
    code = client.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=5.0).status_code
    if code != 200:
        raise SidecarError(f"llama-server did not accept Sentinel's API key (HTTP {code})")


def _model_mb(path: Path) -> float:
    return Path(path).stat().st_size / MIB


def vram_needed_mb(model_mb: float, n_ctx: int) -> float:
    """Rough VRAM need with every layer on the GPU: the weights, the KV cache (at most ~0.12 MB per
    context token for these models) and work buffers. On the safe side: measured on the RTX 3050
    (2026-09-27) the 7B at 4096 context used 4.5 GB (estimate 5.1) and the 1.5B at 2048 used
    1.1 GB (estimate 1.6)."""
    return model_mb + int(n_ctx) * 0.12 + 300.0


def _own_vram_mb(before: Optional[float], after: Optional[float], model_path: Path) -> float:
    # VRAM used after loading minus before (NVML can't report per-process use on Windows), but
    # never less than most of the weights, in case another program freed memory meanwhile.
    measured = (after or 0.0) - (before or 0.0)
    return round(max(measured, _model_mb(model_path) * 0.8), 1)


@dataclass
class _Server:
    proc: subprocess.Popen
    port: int
    key: str
    job: Optional[JobObject]
    model_path: Path
    n_ctx: int
    own_vram_mb: float


class LlamaSidecar:
    def __init__(self, transport: Optional[httpx.BaseTransport] = None):
        self._lock = threading.Lock()
        self._server: Optional[_Server] = None
        self._pending: Optional[subprocess.Popen] = None   # a server that is still starting
        self._cancel = threading.Event()
        self._transport = transport                         # tests plug in a fake server here
        self.last_error: Optional[str] = None

    # ── status ────────────────────────────────────────────────────
    def unavailable_reason(self) -> Optional[str]:
        """Cheap check (no hashing): why the GPU engine can't be used, or None."""
        if sys.platform != "win32":
            return "the GPU engine is built for Windows only"
        if os.environ.get("SENTINEL_DISABLE_LLAMA") == "1":
            return "local models are switched off (SENTINEL_DISABLE_LLAMA=1)"
        if os.environ.get("SENTINEL_FORCE_CPU") == "1":
            return "the GPU engine is switched off (SENTINEL_FORCE_CPU=1)"
        if not MANIFEST_PATH.exists():
            return "the binary hash list backend/llama-bin.sha256.json is missing"
        if not ZIP_PATH.exists() and not (BIN_DIR / SERVER_EXE).exists():
            return "the llama.cpp binaries are missing (backend/llama-bin.zip)"
        if not gpu_monitor.snapshot().get("available"):
            return "no NVIDIA GPU found"
        return cuda_dll_dirs()[1]

    def _alive(self) -> Optional[_Server]:
        with self._lock:
            server = self._server
        return server if server is not None and server.proc.poll() is None else None

    def running(self) -> bool:
        return self._alive() is not None

    def own_vram_mb(self) -> float:
        server = self._alive()
        return server.own_vram_mb if server else 0.0

    def status(self) -> Dict[str, Any]:
        reason = self.unavailable_reason()
        server = self._alive()
        return {"available": reason is None, "reason": reason, "running": server is not None,
                "model": server.model_path.name if server else None,
                "vram_mb": server.own_vram_mb if server else 0.0, "last_error": self.last_error}

    def fits(self, model_path: Path, n_ctx: int) -> Tuple[bool, str]:
        """Would this model fit in the free VRAM while leaving room for the owner's programs?"""
        gpu = gpu_monitor.snapshot(fresh=True)
        used, total = gpu.get("vram_used_mb"), gpu.get("vram_total_mb")
        if not gpu.get("available") or used is None or not total:
            return False, "no VRAM reading from the GPU"
        need = vram_needed_mb(_model_mb(model_path), n_ctx)
        free = total - used
        if free - need < RESERVE_MB:
            return False, (f"needs about {need / 1024:.1f} GB of VRAM and {max(free, 0.0) / 1024:.1f} GB is free "
                           f"(Sentinel keeps {RESERVE_MB / 1024:.0f} GB free for your other programs)")
        if vram_pressure_percent(used + need, total, need) >= MAX_PRESSURE_AFTER:
            return False, "other programs already use most of the VRAM that would be left"
        return True, f"needs about {need / 1024:.1f} GB of VRAM, {free / 1024:.1f} GB free"

    # ── start / stop ──────────────────────────────────────────────
    def start(self, model_path: Path, n_ctx: int = 4096, n_gpu_layers: int = 99) -> "SidecarLLM":
        """Start llama-server with this model and return an engine for ai_service. Blocks until the
        model is loaded. On failure raises SidecarError and leaves nothing running."""
        model_path = Path(model_path)
        reason = self.unavailable_reason()
        if reason:
            raise SidecarError(reason)
        self.stop()                                   # one server at a time
        with self._lock:
            self._cancel.clear()
        key = None
        try:
            exe = ensure_binaries()
            cuda_dirs, why = cuda_dll_dirs()
            if why:
                raise SidecarError(why)
            key = secrets.token_urlsafe(32)
            redaction.register(key)
            port = _free_port()
            before = gpu_monitor.snapshot(fresh=True).get("vram_used_mb")
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOGS_DIR / "llama-server.log"
            with open(log_path, "wb") as log_file:      # the child keeps its own handle
                proc = subprocess.Popen(
                    build_command(exe, model_path, port, n_ctx, n_gpu_layers),
                    cwd=str(BIN_DIR), env=build_env(key, cuda_dirs),
                    stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
                    creationflags=_creation_flags())
            job = None
            try:
                job = JobObject.for_pid(proc.pid)
                with self._lock:
                    self._pending = proc
                with self._client() as client:
                    self._wait_healthy(client, proc, port, log_path)
                    _verify_listener(proc.pid, port)
                    _verify_auth(client, port, key)
                own = _own_vram_mb(before, gpu_monitor.snapshot(fresh=True).get("vram_used_mb"), model_path)
                with self._lock:
                    self._pending = None
                    if self._cancel.is_set() or proc.poll() is not None:
                        raise SidecarError("the GPU engine start was cancelled (Sentinel had to free resources)")
                    self._server = _Server(proc, port, key, job, model_path, int(n_ctx), own)
            except BaseException:
                with self._lock:
                    if self._pending is proc:
                        self._pending = None
                _kill(proc)
                if job is not None:
                    job.close()
                raise
        except SidecarError as e:
            if key:
                redaction.unregister(key)
            self.last_error = str(e)
            raise
        except Exception as e:
            if key:
                redaction.unregister(key)
            self.last_error = f"the GPU engine failed to start ({type(e).__name__}: {e})"
            raise SidecarError(self.last_error) from None
        self.last_error = None
        print(f"[GPU engine] {model_path.name} loaded on the GPU (about {own / 1024:.1f} GB of VRAM)")
        return SidecarLLM(self, model_path)

    def _wait_healthy(self, client: httpx.Client, proc: subprocess.Popen, port: int, log_path: Path) -> None:
        # /health carries nothing private, so it may be asked before the port owner is confirmed.
        deadline = time.monotonic() + START_TIMEOUT_S
        while True:
            if self._cancel.is_set():
                raise SidecarError("the GPU engine start was cancelled (Sentinel had to free resources)")
            code = proc.poll()
            if code is not None:
                raise SidecarError(f"llama-server stopped while loading the model (exit code {code}); "
                                   f"last log lines: {_log_tail(log_path)}")
            try:
                if client.get(f"http://{HOST}:{port}/health", timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise SidecarError(f"llama-server was not ready after {int(START_TIMEOUT_S)} s")
            time.sleep(0.25)

    def stop(self) -> None:
        """Stop the server (or a start in progress) and free its VRAM. Safe to call any time."""
        with self._lock:
            self._cancel.set()
            server, self._server = self._server, None
            pending = self._pending
        if pending is not None:
            _kill(pending)                            # start() notices and cleans up
        if server is None:
            return
        _kill(server.proc)
        if server.job is not None:
            server.job.close()
        redaction.unregister(server.key)
        print("[GPU engine] llama-server stopped; its VRAM is free again")

    # ── inference ─────────────────────────────────────────────────
    def _client(self) -> httpx.Client:
        return httpx.Client(trust_env=False, transport=self._transport, timeout=httpx.Timeout(10.0, connect=5.0))

    def complete_stream(self, prompt: str, max_tokens: int = 512, stop: Optional[List[str]] = None) -> Iterator[str]:
        """Stream the continuation of `prompt` piece by piece. Closing the generator early closes the
        connection, which makes llama-server stop generating."""
        server = self._alive()
        if server is None:
            raise SidecarError("the GPU engine is not running (load the model again)")
        body = {"prompt": prompt, "n_predict": int(max_tokens), "stream": True,
                "cache_prompt": True, "stop": list(stop or [])}
        headers = {"Authorization": f"Bearer {server.key}"}
        with self._client() as client:
            with client.stream("POST", f"http://{HOST}:{server.port}/completion", json=body,
                               headers=headers, timeout=httpx.Timeout(120.0, connect=5.0)) as r:
                if r.status_code != 200:
                    raise SidecarError(f"llama-server answered HTTP {r.status_code}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        event = json.loads(data)
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("error"):
                        raise SidecarError("llama-server reported an error while generating")
                    text = event.get("content") or ""
                    if text:
                        yield text
                    if event.get("stop"):
                        return


class SidecarLLM:
    """Stands in for llama_cpp.Llama in ai_service.generate_stream (streaming calls only):
    calling it yields {"choices": [{"text": ...}]} chunks."""
    n_gpu_layers = 99

    def __init__(self, sidecar: LlamaSidecar, model_path: Path):
        self._sidecar = sidecar
        self.model_path = Path(model_path)

    def __call__(self, prompt: str, max_tokens: int = 512, stop: Optional[List[str]] = None,
                 stream: bool = True, **_ignored) -> Iterator[Dict[str, Any]]:
        for text in self._sidecar.complete_stream(prompt, max_tokens=max_tokens, stop=stop):
            yield {"choices": [{"text": text}]}


llama_sidecar = LlamaSidecar()
