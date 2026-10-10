"""
GPU engine (llama-server sidecar) and model-loading tests.

No GPU, real binaries or internet needed: binaries are tiny fake files in a temp folder,
llama-server is an httpx MockTransport and processes are fakes. The last test starts the REAL
server on the GPU when it can (Windows + binaries + NVIDIA GPU + the 1.5B model, read-only);
everywhere else it is skipped.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.core import gpu_monitor as gm
from app.core import llama_sidecar as ls
from app.core import model_registry as mr

FAKE_FILES = {"llama-server.exe": b"MZ fake server", "ggml-base.dll": b"fake ggml", "llama.dll": b"fake llama"}
HEAVY = "qwen2.5-7b-instruct-q4_k_m.gguf"
LIGHT = "qwen2.5-1.5b-instruct-q4_k_m.gguf"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_zip(path: Path, files: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


@pytest.fixture()
def fake_bins(tmp_path, monkeypatch):
    zpath = tmp_path / "llama-bin.zip"
    _write_zip(zpath, FAKE_FILES)
    manifest = {"zip_sha256": _sha(zpath.read_bytes()),
                "files": {n: {"sha256": _sha(b), "bytes": len(b), "zip_path": n} for n, b in FAKE_FILES.items()}}
    mpath = tmp_path / "llama-bin.sha256.json"
    mpath.write_text(json.dumps(manifest))
    bindir = tmp_path / "llama-bin"
    monkeypatch.setattr(ls, "ZIP_PATH", zpath)
    monkeypatch.setattr(ls, "MANIFEST_PATH", mpath)
    monkeypatch.setattr(ls, "BIN_DIR", bindir)
    return SimpleNamespace(zip=zpath, manifest=mpath, bindir=bindir, data=manifest)


# ── binaries ───────────────────────────────────────────────────────
def test_binaries_are_extracted_and_verified(fake_bins):
    exe = ls.ensure_binaries()
    assert exe == fake_bins.bindir / "llama-server.exe"
    for name, data in FAKE_FILES.items():
        assert (fake_bins.bindir / name).read_bytes() == data
    assert not list(fake_bins.bindir.glob("*.partial"))


def test_changed_binary_is_restored_from_the_zip(fake_bins):
    ls.ensure_binaries()
    (fake_bins.bindir / "llama.dll").write_bytes(b"tampered")
    ls.ensure_binaries()
    assert (fake_bins.bindir / "llama.dll").read_bytes() == FAKE_FILES["llama.dll"]


def test_zip_with_a_changed_file_is_refused(fake_bins):
    _write_zip(fake_bins.zip, dict(FAKE_FILES, **{"llama.dll": b"evil build"}))
    fake_bins.data["zip_sha256"] = _sha(fake_bins.zip.read_bytes())    # zip hash matches, file hash doesn't
    fake_bins.manifest.write_text(json.dumps(fake_bins.data))
    with pytest.raises(ls.SidecarError, match="llama.dll inside backend/llama-bin.zip does not match"):
        ls.ensure_binaries()
    assert not (fake_bins.bindir / "llama.dll").exists()               # never put in place


def test_replaced_zip_is_refused(fake_bins):
    _write_zip(fake_bins.zip, dict(FAKE_FILES, extra=b"x"))            # manifest keeps the old zip hash
    with pytest.raises(ls.SidecarError, match="llama-bin.zip does not match its SHA-256"):
        ls.ensure_binaries()


def test_unknown_program_file_blocks_the_gpu_engine(fake_bins):
    ls.ensure_binaries()
    (fake_bins.bindir / "version.dll").write_bytes(b"planted")         # DLL hijacking attempt
    with pytest.raises(ls.SidecarError, match="unexpected program file"):
        ls.ensure_binaries()
    (fake_bins.bindir / "version.dll").unlink()
    (fake_bins.bindir / "README.txt").write_text("not a program")      # harmless files are fine
    ls.ensure_binaries()


@pytest.mark.parametrize("bad_name", ["../evil.dll", "sub/evil.dll", "C:evil.dll", ".."])
def test_hash_list_rejects_path_names(fake_bins, bad_name):
    fake_bins.data["files"][bad_name] = {"sha256": "0" * 64}
    fake_bins.manifest.write_text(json.dumps(fake_bins.data))
    with pytest.raises(ls.SidecarError, match="bad entry"):
        ls.ensure_binaries()


def test_missing_hash_list_is_refused(fake_bins):
    fake_bins.manifest.unlink()
    with pytest.raises(ls.SidecarError, match="missing"):
        ls.ensure_binaries()


# ── process setup ─────────────────────────────────────────────────
def test_command_line_is_local_and_holds_no_key():
    cmd = ls.build_command(Path("C:/bin/llama-server.exe"), Path("C:/m/model.gguf"), 5555, 2048, 99)
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--port") + 1] == "5555"
    joined = " ".join(cmd)
    assert "api-key" not in joined and "KEY" not in joined
    for download_flag in ("-hf", "--hf-repo", "-mu", "--model-url", "-dr", "--docker-repo"):
        assert download_flag not in cmd


def test_child_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "session-secret-123")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")
    monkeypatch.setenv("PATH", "C:\\Users\\me\\Downloads;C:\\tools")
    env = ls.build_env("KEY-abc-123", ("C:\\venv\\nvidia\\cuda_runtime\\bin",))
    assert env["LLAMA_API_KEY"] == "KEY-abc-123"
    for leaked in ("SENTINEL_SESSION_TOKEN", "HTTPS_PROXY", "LLAMA_ARG_HOST"):
        assert leaked not in env
    path = env["PATH"].split(";")
    assert path[0] == str(ls.BIN_DIR) and path[1] == "C:\\venv\\nvidia\\cuda_runtime\\bin"
    assert "Downloads" not in env["PATH"] and "tools" not in env["PATH"]


def test_verify_auth_demands_the_key():
    def open_server(request):
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(open_server)) as c:
        with pytest.raises(ls.SidecarError, match="without the API key"):
            ls._verify_auth(c, 5555, "K-123456")

    def proper(request):
        ok = request.headers.get("authorization") == "Bearer K-123456"
        return httpx.Response(200 if ok else 401, json={})
    with httpx.Client(transport=httpx.MockTransport(proper)) as c:
        ls._verify_auth(c, 5555, "K-123456")


def test_verify_listener_checks_port_owner(monkeypatch):
    import psutil

    def conn(ip, port):
        return SimpleNamespace(status=psutil.CONN_LISTEN, laddr=SimpleNamespace(ip=ip, port=port))

    def fake_process(conns):
        return lambda pid: SimpleNamespace(connections=lambda kind="inet": conns)

    monkeypatch.setattr(psutil, "Process", fake_process([conn("127.0.0.1", 5555)]))
    ls._verify_listener(1, 5555)
    monkeypatch.setattr(psutil, "Process", fake_process([conn("127.0.0.1", 6000)]))
    with pytest.raises(ls.SidecarError, match="not held"):
        ls._verify_listener(1, 5555)
    monkeypatch.setattr(psutil, "Process", fake_process([conn("0.0.0.0", 5555)]))
    with pytest.raises(ls.SidecarError, match="beyond this PC"):
        ls._verify_listener(1, 5555)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects")
def test_job_object_ends_the_child_when_closed():
    ping = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "PING.EXE")
    p = subprocess.Popen([ping, "-n", "30", "127.0.0.1"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        job = ls.JobObject.for_pid(p.pid)
        assert p.poll() is None
        job.close()
        assert p.wait(timeout=10) is not None
    finally:
        if p.poll() is None:
            p.kill()


# ── streaming ─────────────────────────────────────────────────────
def _running_sidecar(handler):
    sc = ls.LlamaSidecar(transport=httpx.MockTransport(handler))
    proc = SimpleNamespace(poll=lambda: None, pid=4242)
    sc._server = ls._Server(proc=proc, port=5555, key="KEY-xyz-123", job=None,
                            model_path=Path(LIGHT), n_ctx=2048, own_vram_mb=1500.0)
    return sc


def test_stream_sends_key_and_parses_events():
    seen = {}

    def handler(request):
        seen.update(auth=request.headers.get("authorization"), url=str(request.url),
                    body=json.loads(request.content))
        events = [{"content": "Hel", "stop": False}, {"content": "lo", "stop": False},
                  {"content": "", "stop": True, "timings": {"predicted_per_second": 44.0}}]
        return httpx.Response(200, text="".join(f"data: {json.dumps(e)}\n\n" for e in events),
                              headers={"content-type": "text/event-stream"})

    sc = _running_sidecar(handler)
    assert list(sc.complete_stream("PROMPT", max_tokens=32, stop=["<|im_end|>"])) == ["Hel", "lo"]
    assert seen["auth"] == "Bearer KEY-xyz-123"
    assert seen["url"] == "http://127.0.0.1:5555/completion"
    assert seen["body"] == {"prompt": "PROMPT", "n_predict": 32, "stream": True,
                            "cache_prompt": True, "stop": ["<|im_end|>"]}
    assert sc.own_vram_mb() == 1500.0 and sc.running()


def test_stream_error_status_raises():
    sc = _running_sidecar(lambda request: httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    with pytest.raises(ls.SidecarError, match="HTTP 401"):
        list(sc.complete_stream("x"))


def test_stream_without_server_raises():
    with pytest.raises(ls.SidecarError, match="not running"):
        list(ls.LlamaSidecar().complete_stream("x"))


def test_generate_stream_runs_on_the_gpu_engine(monkeypatch):
    from app.core.ai_service import AIService
    from app.core.resource_governor import SystemState, resource_governor
    monkeypatch.setattr(resource_governor, "state", SystemState.INTERACTIVE)

    class FakeSidecar:
        def complete_stream(self, prompt, max_tokens=512, stop=None):
            assert prompt.endswith("<|im_start|>assistant\n") and stop == ["<|im_end|>"]
            yield from ["Hi", " there"]

    svc = AIService()
    svc.llm, svc.engine = ls.SidecarLLM(FakeSidecar(), Path(LIGHT)), "gpu"
    assert "".join(svc.generate_stream("hello", system_prompt="sys")) == "Hi there"


# ── VRAM ──────────────────────────────────────────────────────────
def _snap(used, total=8192.0):
    return dict(gm._empty(), available=True, vram_used_mb=used, vram_total_mb=total,
                vram_percent=round(used / total * 100, 1), source="nvml")


@pytest.mark.parametrize("used,expected", [(1000.0, True), (2500.0, False)])
def test_fit_check_keeps_room_for_other_programs(monkeypatch, tmp_path, used, expected):
    model = tmp_path / HEAVY
    model.write_bytes(b"x")
    monkeypatch.setattr(ls, "_model_mb", lambda p: 4466.0)            # the real 7B file size
    monkeypatch.setattr(ls.gpu_monitor, "snapshot", lambda fresh=False: _snap(used))
    ok, why = ls.LlamaSidecar().fits(model, 4096)
    assert ok is expected, why


def test_fit_check_without_gpu_reading(monkeypatch, tmp_path):
    monkeypatch.setattr(ls.gpu_monitor, "snapshot", lambda fresh=False: gm._empty())
    assert ls.LlamaSidecar().fits(tmp_path / HEAVY, 4096)[0] is False


def test_vram_pressure_ignores_sentinels_own_model():
    assert gm.vram_pressure_percent(6500, 8192, 0) == 79.3                  # nothing of ours loaded
    assert gm.vram_pressure_percent(6500, 8192, 5500) == 37.1              # 7B loaded, others use 1 GB
    assert gm.vram_pressure_percent(8100, 8192, 5500) >= 95.0              # others ran the GPU full
    assert gm.effective_vram_percent(gm._empty(), 5500) == 0.0


def test_governor_uses_vram_pressure(monkeypatch):
    from app.core.resource_governor import ResourceGovernor
    monkeypatch.setattr("app.core.resource_governor.gpu_monitor.snapshot", lambda fresh=False: _snap(6500.0))
    monkeypatch.setattr("app.core.resource_governor.llama_sidecar.own_vram_mb", lambda: 5500.0)
    with patch("psutil.cpu_percent", return_value=10.0), \
         patch("psutil.virtual_memory", return_value=SimpleNamespace(percent=20.0)):
        assert ResourceGovernor()._read_metrics() == (10.0, 20.0, 37.1)


# ── model registry ────────────────────────────────────────────────
def _old_registry(active):
    return {"active_profile": active,
            "profiles": {k: v for k, v in copy.deepcopy(mr.DEFAULT_REGISTRY["profiles"]).items() if k != "auto"}}


def test_registry_moves_the_old_default_to_auto(tmp_path, monkeypatch):
    f = tmp_path / "models.json"
    f.write_text(json.dumps(_old_registry("lightweight")))
    monkeypatch.setattr(mr, "REGISTRY_FILE", f)
    assert mr.ModelRegistry().get_active_id() == "auto"
    saved = json.loads(f.read_text())
    assert saved["version"] == 2 and list(saved["profiles"])[0] == "auto" and "heavy" in saved["profiles"]


def test_registry_keeps_an_explicit_choice(tmp_path, monkeypatch):
    f = tmp_path / "models.json"
    f.write_text(json.dumps(_old_registry("heavy")))
    monkeypatch.setattr(mr, "REGISTRY_FILE", f)
    reg = mr.ModelRegistry()
    assert reg.get_active_id() == "heavy" and "auto" in reg.get_all_profiles()


def test_new_registry_defaults_to_auto_without_sharing_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "REGISTRY_FILE", tmp_path / "models.json")
    reg = mr.ModelRegistry()
    assert reg.get_active_id() == "auto" and (tmp_path / "models.json").exists()
    reg.data["profiles"]["auto"]["name"] = "changed"
    assert mr.DEFAULT_REGISTRY["profiles"]["auto"]["name"] == "Auto (best for this PC)"
    reg.data["active_profile"] = "gone"
    assert reg.get_active_id() == "auto"


# ── load plan ─────────────────────────────────────────────────────
class _FakeRegistry:
    def __init__(self, folder: Path, active: str, downloaded):
        self.folder, self.active = folder, active
        self.profiles = copy.deepcopy(mr.DEFAULT_REGISTRY["profiles"])
        for pid in downloaded:
            (folder / self.profiles[pid]["filename"]).write_bytes(b"gguf")

    def get_active_id(self):
        return self.active

    def get_all_profiles(self):
        return self.profiles

    def get_model_path(self, filename):
        return self.folder / filename


@pytest.fixture()
def plan(tmp_path, monkeypatch):
    from app.core import ai_service as ai_mod
    env = SimpleNamespace(gpu_reason=None, start_error=None, calls=[],
                          fits=lambda path, n_ctx: (True, "fits"))
    sc = ai_mod.llama_sidecar
    monkeypatch.setattr(sc, "unavailable_reason", lambda: env.gpu_reason)
    monkeypatch.setattr(sc, "fits", lambda path, n_ctx: env.fits(path, n_ctx))
    monkeypatch.setattr(sc, "stop", lambda: env.calls.append(("stop",)))
    monkeypatch.setattr(sc, "running", lambda: True)

    def start(path, n_ctx=4096, n_gpu_layers=99):
        env.calls.append(("gpu", Path(path).name))
        if env.start_error:
            raise ls.SidecarError(env.start_error)
        return ls.SidecarLLM(sc, path)
    monkeypatch.setattr(sc, "start", start)

    class FakeLlama:
        def __init__(self, model_path, **kwargs):
            env.calls.append(("cpu", Path(model_path).name))
            assert kwargs["n_gpu_layers"] == 0

    def make(active, downloaded):
        monkeypatch.setattr(mr, "model_registry", _FakeRegistry(tmp_path, active, downloaded))
        svc = ai_mod.AIService()
        svc._llama_available, svc._llama_cls = True, FakeLlama
        return svc
    env.make = make
    return env


def _loads(env):
    return [c for c in env.calls if c[0] != "stop"]


def test_auto_picks_the_7b_on_the_gpu(plan):
    svc = plan.make("auto", ["heavy", "lightweight"])
    assert svc.load_model() is True
    assert (svc.engine, svc.loaded_profile_id) == ("gpu", "heavy")
    assert _loads(plan) == [("gpu", HEAVY)]
    assert svc.loaded_info()["engine"] == "gpu"


def test_auto_takes_the_small_model_when_the_7b_does_not_fit(plan):
    plan.fits = lambda path, n_ctx: ("7b" not in path.name, "too big for the free VRAM")
    svc = plan.make("auto", ["heavy", "lightweight"])
    assert svc.load_model() is True
    assert (svc.engine, svc.loaded_profile_id) == ("gpu", "lightweight")
    assert any("7B" in n and "too big" in n for n in svc.load_notes)


def test_auto_falls_back_to_cpu_without_gpu_engine(plan):
    plan.gpu_reason = "no NVIDIA GPU found"
    svc = plan.make("auto", ["heavy", "lightweight"])
    assert svc.load_model() is True
    assert (svc.engine, svc.loaded_profile_id) == ("cpu", "lightweight")
    assert _loads(plan) == [("cpu", LIGHT)]
    assert "GPU engine: no NVIDIA GPU found" in svc.load_notes


def test_failed_gpu_starts_end_on_the_cpu_with_reasons(plan):
    plan.start_error = "llama-server stopped while loading the model"
    svc = plan.make("auto", ["heavy", "lightweight"])
    assert svc.load_model() is True and svc.engine == "cpu"
    assert _loads(plan) == [("gpu", HEAVY), ("gpu", LIGHT), ("cpu", LIGHT)]
    assert sum("stopped while loading" in n for n in svc.load_notes) == 2


def test_named_profile_runs_on_the_cpu_when_the_gpu_is_unavailable(plan):
    plan.gpu_reason = "the GPU engine is switched off (SENTINEL_FORCE_CPU=1)"
    svc = plan.make("heavy", ["heavy", "lightweight"])
    assert svc.load_model() is True
    assert (svc.engine, svc.loaded_profile_id) == ("cpu", "heavy")


def test_nothing_downloaded_reports_why(plan):
    svc = plan.make("auto", [])
    assert svc.load_model() is False and svc.llm is None
    assert "not downloaded" in svc.last_load_error


def test_unload_during_load_cancels_it(plan, monkeypatch):
    from app.core import ai_service as ai_mod
    svc = plan.make("auto", ["heavy"])
    real_start = ai_mod.llama_sidecar.start

    def start_then_pressure(path, n_ctx=4096, n_gpu_layers=99):
        llm = real_start(path, n_ctx, n_gpu_layers)
        svc.unload_model()                   # the governor frees resources mid-load
        return llm
    monkeypatch.setattr(ai_mod.llama_sidecar, "start", start_then_pressure)
    assert svc.load_model() is False and svc.llm is None
    assert "cancelled" in svc.last_load_error
    assert ("stop",) in plan.calls


def test_dead_gpu_engine_is_noticed(plan, monkeypatch):
    from app.core import ai_service as ai_mod
    svc = plan.make("auto", ["heavy"])
    assert svc.load_model() is True
    monkeypatch.setattr(ai_mod.llama_sidecar, "running", lambda: False)
    svc.check_engine()
    assert svc.llm is None and "stopped unexpectedly" in svc.last_load_error


# ── API ───────────────────────────────────────────────────────────
def test_api_models_shape(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "models-shape-token")
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/models", headers={"X-Sentinel-Session": "models-shape-token"})
    assert r.status_code == 200
    data = r.json()
    ids = [p["id"] for p in data["profiles"]]
    assert isinstance(data["active_profile"], str) and data["active_profile"] in ids
    assert "auto" in ids and all("name" in p and "downloaded" in p for p in data["profiles"])
    assert {"available", "reason", "running", "vram_mb"} <= set(data["gpu_engine"])
    assert data["loaded"] is None or data["loaded"]["engine"] in ("gpu", "cpu")
    health = client.get("/health").json()
    assert health["engine_status"] in ("UNLOADED", "GPU", "CPU", "UNAVAILABLE")


# ── real GPU (skipped unless everything is there) ─────────────────
REAL_MODEL = Path(os.environ.get("USERPROFILE", "~")) / "AppData" / "Roaming" / "sentinel" / "models" / LIGHT


def test_real_gpu_engine_end_to_end():
    if sys.platform != "win32":
        pytest.skip("GPU engine runs on Windows only")
    if not REAL_MODEL.exists():
        pytest.skip("the 1.5B model is not downloaded")
    sc = ls.LlamaSidecar()
    reason = sc.unavailable_reason()
    if reason:
        pytest.skip(f"GPU engine unavailable: {reason}")
    ok, why = sc.fits(REAL_MODEL, 2048)
    if not ok:
        pytest.skip(f"not enough free VRAM right now: {why}")
    import psutil
    llm = sc.start(REAL_MODEL, n_ctx=2048)
    server = sc._alive()
    try:
        assert server is not None
        with httpx.Client(trust_env=False) as c:
            base = f"http://127.0.0.1:{server.port}"
            assert c.get(f"{base}/props").status_code == 401
            assert c.get(f"{base}/props", headers={"Authorization": "Bearer wrong-key"}).status_code == 401
        cmdline = " ".join(psutil.Process(server.proc.pid).cmdline())
        assert server.key not in cmdline and "127.0.0.1" in cmdline
        prompt = "<|im_start|>user\nSay hello in three words.<|im_end|>\n<|im_start|>assistant\n"
        text = "".join(c["choices"][0]["text"] for c in llm(prompt=prompt, max_tokens=16, stop=["<|im_end|>"]))
        assert text.strip()
        assert sc.own_vram_mb() > 500
    finally:
        sc.stop()
    assert not sc.running()
    assert server.proc.poll() is not None
