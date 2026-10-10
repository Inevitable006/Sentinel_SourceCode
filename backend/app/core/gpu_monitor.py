"""
GPU monitor: one cached, in-process reading of NVIDIA GPU stats for the whole backend.

Why this exists: the resource governor used to start an `nvidia-smi` process every
5 seconds (and the skill router twice per GPU-skill call). Each spawn costs tens of
milliseconds up to 2 seconds and ran on the asyncio event loop, so chat streaming
could stall. NVML (the library nvidia-smi itself uses) answers in well under a
millisecond from inside the process.

Order of preference:
  1. NVML through `pynvml` (pip package `nvidia-ml-py`)
  2. one `nvidia-smi` call, if NVML is missing or failing
  3. "not available"
Readings are cached for CACHE_TTL seconds and shared by every caller.
A failing source is retried after RETRY_AFTER seconds, not on every poll.
snapshot() never raises.
"""
import logging
import subprocess
import threading
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

CACHE_TTL = 2.0       # seconds a reading is reused
RETRY_AFTER = 60.0    # seconds before retrying a source that failed

_SMI_CMD = [
    "nvidia-smi",
    "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
    "--format=csv,noheader,nounits",
]


def _now() -> float:
    return time.monotonic()


def _empty(source: str = "none") -> Dict[str, Any]:
    return {
        "available": False, "name": None,
        "vram_used_mb": None, "vram_total_mb": None, "vram_percent": None,
        "util_percent": None, "temp_c": None, "source": source,
    }


def _num(value) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _percent(used: Optional[float], total: Optional[float]) -> Optional[float]:
    if used is None or not total:
        return None
    return round(used / total * 100.0, 1)


def vram_pressure_percent(used_mb, total_mb, own_mb: float = 0.0) -> float:
    """How full the GPU is for everyone else: VRAM used by other programs as a share of the
    VRAM that Sentinel's own model does not hold. Without a Sentinel model it is plain
    "used / total". With the 7B model loaded (about 5.5 of 8 GB), other programs reach 85 %
    when they use about 2.3 of the remaining 2.7 GB, so the governor frees the model exactly
    when the owner's own work starts running out of VRAM, and not merely because Sentinel's
    model itself is big."""
    if used_mb is None or not total_mb:
        return 0.0
    total = float(total_mb)
    own = max(0.0, min(float(own_mb or 0.0), total - 1.0))
    others = max(0.0, float(used_mb) - own)
    return round(min(100.0, others / (total - own) * 100.0), 1)


def effective_vram_percent(snap: Dict[str, Any], own_mb: float = 0.0) -> float:
    """The VRAM figure the resource governor acts on (0.0 when there is no GPU reading)."""
    if not snap.get("available"):
        return 0.0
    used, total = snap.get("vram_used_mb"), snap.get("vram_total_mb")
    if used is None or not total:
        return float(snap.get("vram_percent") or 0.0)
    return vram_pressure_percent(used, total, own_mb)


class GpuMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_at = 0.0
        self._nvml = None              # the pynvml module, once initialised
        self._handle = None
        self._nvml_retry_at = 0.0
        self._smi_retry_at = 0.0
        self._warned = set()

    # ── public API ──────────────────────────────────────────────
    def snapshot(self, fresh: bool = False) -> Dict[str, Any]:
        """Fresh-enough reading (cached for CACHE_TTL). Blocking at most ~2 s on the nvidia-smi fallback.
        fresh=True skips the cache (used to measure VRAM right before/after loading a model);
        a failing source is still only retried after RETRY_AFTER."""
        with self._lock:
            if not fresh and self._cache is not None and _now() - self._cache_at < CACHE_TTL:
                return dict(self._cache)
            try:
                snap = self._read_nvml() or self._read_smi() or _empty()
            except Exception as e:  # belt and braces: never raise to callers
                self._warn_once("unexpected", f"GPU reading failed: {type(e).__name__}")
                snap = _empty()
            self._cache, self._cache_at = snap, _now()
            return dict(snap)

    def peek(self) -> Dict[str, Any]:
        """Last reading without triggering a new one (safe to call from the event loop)."""
        with self._lock:
            return dict(self._cache) if self._cache is not None else _empty("pending")

    def shutdown(self) -> None:
        with self._lock:
            if self._nvml is not None:
                try:
                    self._nvml.nvmlShutdown()
                except Exception:
                    pass
            self._nvml = None
            self._handle = None
            self._cache = None

    # ── sources ─────────────────────────────────────────────────
    def _read_nvml(self) -> Optional[Dict[str, Any]]:
        if self._nvml is None and _now() < self._nvml_retry_at:
            return None
        try:
            if self._nvml is None:
                import pynvml  # package: nvidia-ml-py
                pynvml.nvmlInit()
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvml = pynvml
            n, h = self._nvml, self._handle
            mem = n.nvmlDeviceGetMemoryInfo(h)
            name = n.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            util = temp = None
            try:
                util = _num(n.nvmlDeviceGetUtilizationRates(h).gpu)
            except Exception:
                pass
            try:
                temp = _num(n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU))
            except Exception:
                pass
            used, total = mem.used / 1048576.0, mem.total / 1048576.0
            return {
                "available": True, "name": name,
                "vram_used_mb": round(used, 1), "vram_total_mb": round(total, 1),
                "vram_percent": _percent(used, total),
                "util_percent": util, "temp_c": temp, "source": "nvml",
            }
        except Exception as e:
            if self._nvml is not None:
                try:
                    self._nvml.nvmlShutdown()
                except Exception:
                    pass
            self._nvml, self._handle = None, None
            self._nvml_retry_at = _now() + RETRY_AFTER
            self._warn_once("nvml", f"NVML unavailable ({type(e).__name__}); using nvidia-smi fallback")
            return None

    def _read_smi(self) -> Optional[Dict[str, Any]]:
        if _now() < self._smi_retry_at:
            return None
        try:
            r = subprocess.run(
                _SMI_CMD, capture_output=True, text=True, timeout=2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode != 0 or not r.stdout.strip():
                raise RuntimeError(f"nvidia-smi exit code {r.returncode}")
            parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
            if len(parts) < 3:
                raise ValueError("unexpected nvidia-smi output")
            used, total = _num(parts[1]), _num(parts[2])
            return {
                "available": True, "name": parts[0] or None,
                "vram_used_mb": used, "vram_total_mb": total,
                "vram_percent": _percent(used, total),
                "util_percent": _num(parts[3]) if len(parts) > 3 else None,
                "temp_c": _num(parts[4]) if len(parts) > 4 else None,
                "source": "nvidia-smi",
            }
        except Exception as e:
            self._smi_retry_at = _now() + RETRY_AFTER
            self._warn_once("smi", f"nvidia-smi unavailable ({type(e).__name__}); GPU stats disabled for now")
            return None

    def _warn_once(self, key: str, msg: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning("[GpuMonitor] %s", msg)


gpu_monitor = GpuMonitor()
