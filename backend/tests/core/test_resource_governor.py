"""
Resource governor state-machine tests.

All psutil / nvidia-smi calls are mocked; no real system load is measured.
The model unload hook is mocked so no AI service is touched.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.resource_governor import ResourceGovernor, SystemState


def _tick(gov, cpu=10.0, ram=10.0):
    """Run one governor check with the given CPU/RAM percentages (no GPU)."""
    with patch("psutil.cpu_percent", return_value=cpu), \
         patch("psutil.virtual_memory", return_value=SimpleNamespace(percent=ram)), \
         patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi")):
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
