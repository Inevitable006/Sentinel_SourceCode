import pytest

from app.core import pure_skill_worker as worker
from app.core.secure_runner import secure_runner
from app.core.skill_router import skill_router
from app.core.safe_process import current_job
from app.core.tool_registry import is_failure

ARGS = {'value': 1, 'from_unit': 'km', 'to_unit': 'm'}
TOOL = 'skill_convert_units'


@pytest.fixture(autouse=True)
def registered():
    from app.core.skill_loader import register_all_skills
    register_all_skills()


def test_approval_and_single_use_token_before_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, 'run_pure', lambda *a: calls.append((a, current_job.get())) or '1000')
    first = secure_runner.execute(TOOL, ARGS, 'synthetic-session', request_id='synthetic-request')
    assert first['status'] == 'needs_confirmation' and not calls
    token = first['token']
    result = secure_runner.execute(TOOL, ARGS, 'synthetic-session', request_id='synthetic-request', token=token)
    assert result['status'] == 'success'
    assert calls == [(('technical_analysis', 'convert_units', ARGS), 'synthetic-request')]
    assert secure_runner.execute(TOOL, ARGS, 'synthetic-session', token=token)['status'] == 'error'
    assert len(calls) == 1


def test_router_never_loads_calculation_module_in_parent(monkeypatch):
    monkeypatch.setattr(skill_router, '_load_module', lambda *a: pytest.fail('parent load'))
    monkeypatch.setattr(skill_router, '_inject_capabilities', lambda *a: pytest.fail('injected service'))
    monkeypatch.setattr(worker, 'run_pure', lambda *a: 'synthetic result')
    assert skill_router._execute_skill_tool('technical_analysis', TOOL, ARGS) == 'synthetic result'


def test_locked_worker_does_not_start(monkeypatch):
    monkeypatch.setattr(worker, 'is_open', lambda: False)
    monkeypatch.setattr(worker, '_run_pure', lambda *a: pytest.fail('worker started'))
    assert is_failure(worker.run_pure('technical_analysis', 'convert_units', ARGS))


def test_lock_cancels_request_and_discards_late_result(monkeypatch):
    cancelled = []
    monkeypatch.setattr(worker, 'is_open', lambda: True)
    monkeypatch.setattr(worker.safe_process, 'cancel_job', cancelled.append)
    def complete_after_lock(*args):
        worker._cancel_on_lock()
        return 'late success'
    monkeypatch.setattr(worker, '_run_pure', complete_after_lock)
    token = current_job.set('synthetic-lock-request')
    try:
        result = worker.run_pure('technical_analysis', 'convert_units', ARGS)
        assert is_failure(result)
        assert cancelled == ['synthetic-lock-request']
        assert not worker._active
        assert current_job.get() == 'synthetic-lock-request'
    finally:
        current_job.reset(token)
