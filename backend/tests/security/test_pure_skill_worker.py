import json
import hashlib
import threading

import pytest

from app.core import pure_skill_worker as worker
from app.core.tool_registry import is_failure


@pytest.mark.parametrize('skill,tool,args,key,value', [
    ('technical_analysis', 'convert_units', {'value': 1, 'from_unit': 'km', 'to_unit': 'm'}, 'result', 1000),
    ('technical_analysis', 'estimate_transfer', {'size': 1, 'size_unit': 'MB', 'bandwidth_mbps': 10, 'utilization_percent': 100}, 'seconds', .8),
    ('business_analysis', 'unit_economics', {'price': 10, 'variable_cost': 4, 'fixed_cost': 60}, 'break_even_units', 10),
    ('business_analysis', 'campaign_metrics', {'spend': 200, 'impressions': 10000, 'clicks': 400, 'conversions': 20, 'revenue': 800}, 'click_through_rate_percent', 4),
])
def test_real_contained_calculation(skill, tool, args, key, value):
    result = worker.run_pure(skill, tool, args)
    assert not is_failure(result), result
    assert json.loads(result)[key] == pytest.approx(value)


def test_child_failure_is_not_success():
    result = worker.run_pure('technical_analysis', 'convert_units', {'value': 1, 'from_unit': 'kg', 'to_unit': 'm'})
    assert is_failure(result)
    assert 'dimensions' in result


@pytest.mark.parametrize('args', [{'value': float('nan')}, {'value': []}, {'value': 'x' * 8193}, {'_memory_read': 'forbidden'}])
def test_bad_inputs_never_start_child(monkeypatch, args):
    monkeypatch.setattr(worker, 'run_python', lambda *a, **k: pytest.fail('child started'))
    assert is_failure(worker.run_pure('technical_analysis', 'convert_units', args))


def test_unknown_tool_and_integrity_mismatch_never_start_child(monkeypatch):
    monkeypatch.setattr(worker, 'run_python', lambda *a, **k: pytest.fail('child started'))
    assert is_failure(worker.run_pure('technical_analysis', '__import__', {}))
    monkeypatch.setattr(worker.skill_verifier, 'pinned_hashes', lambda: {})
    assert is_failure(worker.run_pure('technical_analysis', 'convert_units', {}))


@pytest.mark.parametrize('response', [(False, '', 'private error'), (True, '{}', ''), (True, '{"failed": "false", "result": "bad"}', '')])
def test_crash_and_bad_protocol_fail_closed(monkeypatch, response):
    monkeypatch.setattr(worker, 'run_python', lambda *a, **k: response)
    result = worker.run_pure('technical_analysis', 'convert_units', {})
    assert is_failure(result)
    assert 'private error' not in result


def synthetic_skill(monkeypatch, tmp_path, source):
    """Test-only pin/source pair; never changes production modules or pins."""
    folder = tmp_path / 'technical_analysis'
    folder.mkdir()
    data = source.encode('utf-8')
    (folder / '__init__.py').write_bytes(data)
    monkeypatch.setattr(worker, 'SKILLS', tmp_path)
    monkeypatch.setattr(worker.skill_verifier, 'pinned_hashes', lambda: {
        'skills.technical_analysis': hashlib.sha256(data).hexdigest(),
    })


def test_real_request_cancellation_stops_worker(monkeypatch, tmp_path):
    from app.core.safe_process import safe_process, current_job
    synthetic_skill(monkeypatch, tmp_path, 'def convert_units():\n    while True: pass\n')
    started = threading.Event()
    original_track = safe_process._track
    request = 'synthetic-calculator-cancel'
    def track(job, pid):
        original_track(job, pid)
        if job == request:
            started.set()
    monkeypatch.setattr(safe_process, '_track', track)
    results = []
    def execute():
        token = current_job.set(request)
        try:
            results.append(worker.run_pure('technical_analysis', 'convert_units', {}))
        finally:
            current_job.reset(token)
    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert started.wait(5), 'worker did not start'
        safe_process.cancel_job(request)
        thread.join(8)
        assert not thread.is_alive(), 'cancelled worker is still running'
        assert len(results) == 1 and is_failure(results[0])
        assert request not in safe_process.active_processes
    finally:
        safe_process.cancel_job(request)
        thread.join(25)


@pytest.mark.parametrize('size', [20000, 1100000])
def test_real_oversized_output_is_never_accepted(monkeypatch, tmp_path, size):
    synthetic_skill(monkeypatch, tmp_path, f"def convert_units():\n    return 'x' * {size}\n")
    result = worker.run_pure('technical_analysis', 'convert_units', {})
    assert is_failure(result)
    assert len(result) < 200


def test_oversized_source_is_refused_before_launch(monkeypatch, tmp_path):
    synthetic_skill(monkeypatch, tmp_path, '#' * (worker.MAX_SOURCE + 1))
    monkeypatch.setattr(worker, 'run_python', lambda *a, **k: pytest.fail('child started'))
    result = worker.run_pure('technical_analysis', 'convert_units', {})
    assert is_failure(result) and 'source limit' in result


@pytest.mark.parametrize('code', [
    'import socket\ndef convert_units(): return "unexpected"\n',
    'from app.core import vault\ndef convert_units(): return "unexpected"\n',
    'def convert_units():\n    return len(bytearray(900 * 1024 * 1024))\n',
])
def test_real_worker_refuses_backend_network_and_excess_memory(monkeypatch, tmp_path, code):
    synthetic_skill(monkeypatch, tmp_path, code)
    assert is_failure(worker.run_pure('technical_analysis', 'convert_units', {}))


def test_invalid_tool_identifiers_fail_closed():
    assert is_failure(worker.run_pure([], 'convert_units', {}))
    assert is_failure(worker.run_pure('technical_analysis', {}, {}))
