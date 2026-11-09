"""
Resource governor state-machine tests.

All psutil / GPU readings are mocked; no real system load is measured.
The model unload hook is mocked so no AI service is touched.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.gpu_monitor import _empty
from app.core.resource_governor import ResourceGovernor, SystemState

_NO_GPU = _empty()


def _tick(gov, cpu=10.0, ram=10.0):
    """Run one governor check with the given CPU/RAM percentages (no GPU)."""
    with patch("psutil.cpu_percent", return_value=cpu), \
         patch("psutil.virtual_memory", return_value=SimpleNamespace(percent=ram)), \
         patch("psutil.sensors_battery", return_value=None), \
         patch("app.core.resource_governor.desktop_busy", return_value=None), \
         patch("app.core.resource_governor.gpu_monitor.snapshot", return_value=_NO_GPU):
        gov._check_resources()


@pytest.fixture()
def gov():
    g = ResourceGovernor()          # fresh instance, not the process-wide singleton
    g.state = SystemState.INTERACTIVE
    with patch("app.core.ai_service.ai_service.unload_model") as unload:
        g._unload = unload
        yield g


def test_sustained_high_cpu_enters_high_load_and_unloads(gov):
    _tick(gov, cpu=90)
    assert gov.state == SystemState.INTERACTIVE      # one spike is ignored
    _tick(gov, cpu=90)
    assert gov.state == SystemState.HIGH_LOAD
    gov._unload.assert_called()


def test_recovers_to_interactive_after_three_clean_checks(gov):
    _tick(gov, cpu=90)
    _tick(gov, cpu=90)
    assert gov.state == SystemState.HIGH_LOAD
    _tick(gov)
    _tick(gov)
    assert gov.state == SystemState.HIGH_LOAD        # needs 3 clean checks
    _tick(gov)
    assert gov.state == SystemState.INTERACTIVE


def test_recovers_from_emergency(gov):
    _tick(gov, cpu=99)
    _tick(gov, cpu=99)
    assert gov.state == SystemState.EMERGENCY
    for _ in range(3):
        _tick(gov)
    assert gov.state == SystemState.INTERACTIVE


def test_spike_during_recovery_restarts_the_count(gov):
    _tick(gov, cpu=90)
    _tick(gov, cpu=90)
    _tick(gov)
    _tick(gov)
    _tick(gov, cpu=90)                               # load comes back
    _tick(gov)
    _tick(gov)
    assert gov.state == SystemState.HIGH_LOAD
    _tick(gov)
    assert gov.state == SystemState.INTERACTIVE


def test_user_pause_is_not_overridden_by_monitoring(gov):
    gov.set_user_paused(True)
    assert gov.state == SystemState.USER_PAUSED
    gov._unload.assert_called()


def test_low_battery_pauses_and_recovers_when_plugged_in(gov):
    gov.battery = {"percent": 10, "plugged_in": False}
    gov._evaluate(10, 10, 0)
    gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.HIGH_LOAD and gov.pause_reason == "Battery is low"
    gov.battery["plugged_in"] = True
    for _ in range(3):
        gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.INTERACTIVE and gov.pause_reason is None


def test_gpu_heat_pauses_even_with_low_utilization(gov):
    gov.gpu_temp_c = 90
    gov._evaluate(10, 10, 0)
    gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.EMERGENCY
    assert gov.pause_reason == "GPU temperature is high"
    gov.gpu_temp_c = 60
    for _ in range(3):
        gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.INTERACTIVE


def test_sensor_absence_does_not_claim_a_reading_or_pause(gov):
    _tick(gov)
    assert gov.battery is None and gov.gpu_temp_c is None
    assert gov.state == SystemState.INTERACTIVE


def test_fullscreen_pauses_and_recovers_after_exit(gov):
    gov.desktop_busy = True
    for _ in range(2):
        gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.HIGH_LOAD
    assert "Full-screen" in gov.pause_reason
    gov._unload.assert_called_once()
    gov.desktop_busy = False
    for _ in range(3):
        gov._evaluate(10, 10, 0)
    assert gov.state == SystemState.INTERACTIVE
    assert gov.pause_reason is None


@pytest.mark.parametrize("state,expected", [(1, False), (2, True), (3, True), (4, True), (5, False), (6, False), (7, False), (0, None)])
def test_windows_desktop_signal(state, expected):
    import ctypes
    from app.core.resource_governor import desktop_busy

    def query(pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int))[0] = state
        return 0

    with patch("app.core.resource_governor.sys.platform", "win32"), \
         patch("ctypes.WinDLL", create=True) as library:
        library.return_value.SHQueryUserNotificationState.side_effect = query
        assert desktop_busy() is expected


def test_failed_desktop_query_is_unknown():
    from app.core.resource_governor import desktop_busy
    with patch("app.core.resource_governor.sys.platform", "win32"), \
         patch("ctypes.WinDLL", create=True) as library:
        library.return_value.SHQueryUserNotificationState.return_value = -1
        assert desktop_busy() is None
        library.side_effect = OSError("unavailable")
        assert desktop_busy() is None
