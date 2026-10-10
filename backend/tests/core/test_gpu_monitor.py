"""
GPU monitor + governor/skill-router integration (Phase 1, step 1.0).
No real GPU is needed: pynvml and nvidia-smi are faked.
"""
import asyncio
import subprocess
import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core import gpu_monitor as gm
from app.core.resource_governor import ResourceGovernor, SystemState


def _fake_pynvml(used_mb=2048, total_mb=8192, util=37, temp=55,
                 name=b"NVIDIA GeForce RTX 3050", fail_init=False):
    m = types.ModuleType("pynvml")
    m.NVML_TEMPERATURE_GPU = 0
    m.reads = 0

    def init():
        if fail_init:
            raise RuntimeError("NVML Shared Library Not Found")

    def mem(_h):
        m.reads += 1
        return SimpleNamespace(used=used_mb * 1048576, total=total_mb * 1048576)

    m.nvmlInit = init
    m.nvmlShutdown = MagicMock()
    m.nvmlDeviceGetHandleByIndex = lambda i: "gpu0"
    m.nvmlDeviceGetMemoryInfo = mem
    m.nvmlDeviceGetName = lambda h: name
    m.nvmlDeviceGetUtilizationRates = lambda h: SimpleNamespace(gpu=util)
    m.nvmlDeviceGetTemperature = lambda h, sensor: temp
    return m


def _smi(stdout, returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


@pytest.fixture()
def mon():
    m = gm.GpuMonitor()
    yield m
    m.shutdown()


# ── sources ─────────────────────────────────────────────────────

def test_nvml_reading(mon):
    with patch.dict(sys.modules, {"pynvml": _fake_pynvml()}), patch("subprocess.run") as run:
        s = mon.snapshot()
    assert s["available"] is True and s["source"] == "nvml"
    assert s["name"] == "NVIDIA GeForce RTX 3050"
    assert (s["vram_used_mb"], s["vram_total_mb"], s["vram_percent"]) == (2048.0, 8192.0, 25.0)
    assert (s["util_percent"], s["temp_c"]) == (37.0, 55.0)
    run.assert_not_called()


def test_falls_back_to_nvidia_smi_when_pynvml_missing(mon):
    csv = "NVIDIA GeForce RTX 3050, 1024, 8192, 12, 48\n"
    with patch.dict(sys.modules, {"pynvml": None}), patch("subprocess.run", return_value=_smi(csv)) as run:
        s = mon.snapshot()
    assert s["available"] is True and s["source"] == "nvidia-smi"
    assert (s["vram_percent"], s["util_percent"], s["temp_c"]) == (12.5, 12.0, 48.0)
    assert run.call_count == 1
    cmd = run.call_args.args[0]
    assert isinstance(cmd, list) and cmd[0] == "nvidia-smi"      # argument list, no shell
    assert not run.call_args.kwargs.get("shell", False)


def test_falls_back_when_nvml_init_fails(mon):
    with patch.dict(sys.modules, {"pynvml": _fake_pynvml(fail_init=True)}), \
         patch("subprocess.run", return_value=_smi("GPU, 4096, 8192, 50, 60")):
        s = mon.snapshot()
    assert s["source"] == "nvidia-smi" and s["vram_percent"] == 50.0


@pytest.mark.parametrize("error", [FileNotFoundError("nvidia-smi"), subprocess.TimeoutExpired("nvidia-smi", 2)])
def test_nothing_available_never_raises(mon, error):
    with patch.dict(sys.modules, {"pynvml": None}), patch("subprocess.run", side_effect=error):
        s = mon.snapshot()
    assert s["available"] is False and s["source"] == "none" and s["vram_percent"] is None


def test_failed_source_is_not_retried_on_every_poll(mon):
    clock = [1000.0]
    with patch.dict(sys.modules, {"pynvml": None}), \
         patch("app.core.gpu_monitor._now", side_effect=lambda: clock[0]), \
         patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")) as run:
        for _ in range(5):
            clock[0] += gm.CACHE_TTL + 0.1
            mon.snapshot()
        assert run.call_count == 1                     # backed off after the first failure
        clock[0] += gm.RETRY_AFTER + 1
        mon.snapshot()
        assert run.call_count == 2


def test_readings_are_cached_for_ttl(mon):
    fake = _fake_pynvml()
    clock = [100.0]
    with patch.dict(sys.modules, {"pynvml": fake}), patch("app.core.gpu_monitor._now", side_effect=lambda: clock[0]):
        mon.snapshot()
        mon.snapshot()
        assert fake.reads == 1
        clock[0] += gm.CACHE_TTL + 0.1
        mon.snapshot()
        assert fake.reads == 2


def test_peek_never_reads(mon):
    fake = _fake_pynvml()
    with patch.dict(sys.modules, {"pynvml": fake}):
        assert mon.peek()["source"] == "pending"
        assert fake.reads == 0
        mon.snapshot()
        assert mon.peek()["source"] == "nvml" and fake.reads == 1


def test_shutdown_releases_nvml(mon):
    fake = _fake_pynvml()
    with patch.dict(sys.modules, {"pynvml": fake}):
        mon.snapshot()
        mon.shutdown()
    fake.nvmlShutdown.assert_called_once()


# ── governor ────────────────────────────────────────────────────

def _run_loop_briefly(gov, seconds=0.08):
    async def run():
        task = asyncio.ensure_future(gov._monitor_loop())
        await asyncio.sleep(seconds)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(run())


def test_governor_reads_metrics_off_the_event_loop():
    gov = ResourceGovernor()
    gov.poll_interval = 0.01
    main_thread, reader_threads = threading.get_ident(), []

    def fake_read():
        reader_threads.append(threading.get_ident())
        return (10.0, 10.0, 0.0)

    with patch.object(gov, "_read_metrics", side_effect=fake_read):
        _run_loop_briefly(gov)
    assert reader_threads, "monitor loop never read metrics"
    assert all(t != main_thread for t in reader_threads)


def test_governor_survives_a_failing_reading():
    gov = ResourceGovernor()
    gov.poll_interval = 0.01
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("sensor glitch")
        return (10.0, 10.0, 0.0)

    with patch.object(gov, "_read_metrics", side_effect=flaky):
        _run_loop_briefly(gov)
    assert len(calls) >= 2


def test_high_vram_counts_as_high_load():
    gov = ResourceGovernor()
    gov.state = SystemState.INTERACTIVE
    with patch("app.core.ai_service.ai_service.unload_model"):
        gov._evaluate(10.0, 10.0, 90.0)
        gov._evaluate(10.0, 10.0, 90.0)
    assert gov.state == SystemState.HIGH_LOAD


def test_read_metrics_uses_gpu_monitor():
    gov = ResourceGovernor()
    snap = dict(gm._empty(), available=True, vram_percent=40.0, source="nvml")
    with patch("psutil.cpu_percent", return_value=5.0), \
         patch("psutil.virtual_memory", return_value=SimpleNamespace(percent=30.0)), \
         patch("app.core.resource_governor.gpu_monitor.snapshot", return_value=snap), \
         patch("subprocess.run") as run:
        assert gov._read_metrics() == (5.0, 30.0, 40.0)
    run.assert_not_called()


def test_get_status_includes_gpu_without_a_new_reading():
    gov = ResourceGovernor()
    with patch("app.core.resource_governor.gpu_monitor.snapshot") as snap:
        status = gov.get_status()
    assert "gpu" in status and {"state", "cpu_percent", "ram_percent", "manual_override"} <= set(status)
    snap.assert_not_called()


# ── skill router ────────────────────────────────────────────────

def test_skill_router_gpu_checks_use_the_monitor():
    from app.core.skill_router import skill_router
    snap = dict(gm._empty(), available=True, vram_percent=42.0, source="nvml")
    with patch("app.core.skill_router.gpu_monitor.snapshot", return_value=snap), patch("subprocess.run") as run:
        assert skill_router._is_gpu_available() is True
        assert skill_router._get_vram_percent() == 42.0
    run.assert_not_called()


# ── real hardware (skipped on machines without an NVIDIA GPU / NVML) ──

def test_real_gpu_through_nvml_if_present():
    pynvml = pytest.importorskip("pynvml")
    try:
        pynvml.nvmlInit()
        pynvml.nvmlShutdown()
    except Exception:
        pytest.skip("no NVIDIA driver / GPU on this machine")
    m = gm.GpuMonitor()
    try:
        s = m.snapshot()
    finally:
        m.shutdown()
    assert s["available"] is True and s["source"] == "nvml"
    assert s["vram_total_mb"] and s["vram_total_mb"] > 1000
    assert 0.0 <= s["vram_percent"] <= 100.0
    print(f"\n[real GPU] {s['name']}: {s['vram_used_mb']:.0f}/{s['vram_total_mb']:.0f} MB, util {s['util_percent']}%, {s['temp_c']} C")
