"""C1: truthful local readiness without starting optional capabilities."""
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import pytest
from fastapi.testclient import TestClient
from app.core import readiness
from app.db.database import DatabaseLocked

IDS = ['chat', 'dictation', 'speech', 'document_search', 'google', 'backup']


def test_contract_and_failure_isolation(monkeypatch):
    for name in ('_chat', '_dictation', '_speech', '_documents', '_google', '_backup'):
        monkeypatch.setattr(readiness, name, lambda: ('setup_required', 'Use the existing setup controls.'))
    def broken():
        raise RuntimeError('PRIVATE_TOKEN_AND_PATH')
    monkeypatch.setattr(readiness, '_google', broken)
    response = readiness.snapshot()
    assert response['version'] == 1
    assert [r['id'] for r in response['checks']] == IDS
    assert response['checks'][4]['state'] == 'unknown'
    assert response['checks'][5]['state'] == 'setup_required'
    assert 'PRIVATE_TOKEN_AND_PATH' not in str(response)
    for row in response['checks']:
        assert set(row) == {'id', 'label', 'state', 'detail'}
        assert 0 < len(row['label']) <= 80 and 0 < len(row['detail']) <= 400


def test_database_lock_is_not_hidden_as_optional_failure(monkeypatch):
    def locked(): raise DatabaseLocked('locked')
    monkeypatch.setattr(readiness, '_chat', locked)
    with pytest.raises(DatabaseLocked): readiness.snapshot()


def test_chat_requires_selected_model_and_known_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv('SENTINEL_DISABLE_LLAMA', raising=False)
    monkeypatch.setattr(readiness, '_paused', lambda: False)
    engine = SimpleNamespace(llm=None, last_load_error=None, _llama_available=None)
    registry = SimpleNamespace(get_active_id=lambda: 'lightweight',
        get_all_profiles=lambda: {'lightweight': {'filename': 'synthetic.gguf'}},
        get_model_path=lambda name: tmp_path / name)
    monkeypatch.setattr(readiness, '_service', lambda mod, name: engine if mod == 'ai_service' else registry)
    assert readiness._chat()[0] == 'setup_required'
    (tmp_path / 'synthetic.gguf').write_bytes(b'fixture')
    assert readiness._chat()[0] == 'unknown'
    engine._llama_available = True
    assert readiness._chat()[0] == 'ready'
    engine.last_load_error = 'PRIVATE_ERROR'
    assert readiness._chat()[0] == 'unavailable'
    assert 'PRIVATE_ERROR' not in str(readiness._chat())
    monkeypatch.setenv('SENTINEL_DISABLE_LLAMA', '1')
    assert readiness._chat()[0] == 'unavailable'


def test_dictation_uses_cached_probe_without_loading(monkeypatch, tmp_path):
    from app.core import speech_input
    monkeypatch.setattr(readiness, '_paused', lambda: False)
    monkeypatch.setattr(speech_input, 'MODEL_DIR', tmp_path)
    monkeypatch.setattr(speech_input.speech_input, 'status', lambda: pytest.fail('Must not probe/load model'))
    monkeypatch.setattr(speech_input.speech_input, '_runtime_checked', False)
    monkeypatch.setattr(speech_input.speech_input, '_runtime_error', None)
    assert readiness._dictation()[0] == 'setup_required'
    for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'):
        (tmp_path / name).write_bytes(b'fixture')
    assert readiness._dictation()[0] == 'unknown'
    monkeypatch.setattr(speech_input.speech_input, '_runtime_checked', True)
    assert readiness._dictation()[0] == 'ready'
    monkeypatch.setattr(speech_input.speech_input, '_runtime_error', 'PRIVATE_ERROR')
    assert readiness._dictation()[0] == 'unavailable'
    assert 'PRIVATE_ERROR' not in str(readiness._dictation())


def test_speech_does_not_initialize_or_wait(monkeypatch):
    monkeypatch.delitem(sys.modules, 'app.core.voice_service', raising=False)
    assert readiness._speech()[0] == 'unknown'
    assert 'app.core.voice_service' not in sys.modules
    service = SimpleNamespace(_ready=SimpleNamespace(is_set=lambda: True), _engine=object(),
                              thread=SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setitem(sys.modules, 'app.core.voice_service', SimpleNamespace(voice_service=service))
    assert readiness._speech()[0] == 'ready'
    service.thread = SimpleNamespace(is_alive=lambda: False)
    assert readiness._speech()[0] == 'unavailable'


@pytest.mark.parametrize('info,state', [
    ({'installed': False, 'documents': 0, 'indexed': 0, 'pending': 0}, 'setup_required'),
    ({'installed': True, 'documents': 0, 'indexed': 0, 'pending': 0}, 'setup_required'),
    ({'installed': True, 'documents': 2, 'indexed': 1, 'pending': 1}, 'setup_required'),
    ({'installed': True, 'documents': 2, 'indexed': 2, 'pending': 0}, 'ready'),
])
def test_document_coverage(monkeypatch, info, state):
    from app.core import semantic_search
    monkeypatch.setattr(readiness, '_paused', lambda: False)
    monkeypatch.setattr(semantic_search, 'status', lambda: info)
    monkeypatch.setattr(semantic_search, '_load_model', lambda: pytest.fail('Must not load'))
    assert readiness._documents()[0] == state


def test_google_stored_grants_are_not_live_verification(monkeypatch):
    from app.core import google_workspace
    info = {'configured': True, 'connected': True, 'gmail': True, 'calendar': True}
    monkeypatch.setattr(google_workspace, 'status', lambda: info)
    state, detail = readiness._google()
    assert state == 'ready' and 'Live access has not been checked' in detail
    info['calendar'] = False
    assert readiness._google()[0] == 'setup_required'
    info['connected'] = False
    assert readiness._google()[0] == 'setup_required'


def test_backup_check_does_not_create_or_open_archives(monkeypatch, tmp_path):
    from app.core import backup
    folder = tmp_path / 'backups'
    monkeypatch.setattr(backup, 'BACKUP_DIR', folder)
    monkeypatch.setattr(backup, 'create_backup', lambda: pytest.fail('Must not create'))
    assert readiness._backup()[0] == 'setup_required'
    assert not folder.exists()
    folder.mkdir()
    (folder / 'synthetic.sentinelbak').write_bytes(b'not-an-archive')
    state, detail = readiness._backup()
    assert state == 'ready' and 'have not been tested' in detail


def test_endpoint_auth_lock_and_lock_during_checks(monkeypatch):
    from app.main import app
    from app import workspace_routes as ws
    monkeypatch.setenv('SENTINEL_SESSION_TOKEN', 'readiness-test')
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: True)
    probe = Mock(return_value={'version': 1, 'checks': []})
    monkeypatch.setattr(readiness, 'snapshot', probe)
    client = TestClient(app); headers = {'X-Sentinel-Session': 'readiness-test'}
    path = '/api/workspace/readiness'
    assert client.get(path).status_code == 422
    assert client.get(path, headers={'X-Sentinel-Session':'wrong'}).status_code == 401
    probe.assert_not_called()
    assert client.get(path, headers=headers).json() == {'version': 1, 'checks': []}
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: False)
    assert client.get(path, headers=headers).status_code == 423
    assert probe.call_count == 1
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: True)
    def locking():
        monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: False)
        return {'version': 1, 'checks': []}
    monkeypatch.setattr(readiness, 'snapshot', locking)
    assert client.get(path, headers=headers).status_code == 423


def test_real_snapshot_avoids_active_capabilities(monkeypatch):
    from app.core.ai_service import ai_service
    from app.core import speech_input, semantic_search, backup
    from app.main import app
    from app import workspace_routes as ws
    def forbidden(*args, **kwargs): pytest.fail('Readiness must not activate capabilities')
    monkeypatch.setattr(ai_service, 'load_model', forbidden)
    monkeypatch.setattr(ai_service, '_binding_ready', forbidden)
    monkeypatch.setattr(speech_input.speech_input, 'status', forbidden)
    monkeypatch.setattr(semantic_search, '_load_model', forbidden)
    monkeypatch.setattr(backup, 'create_backup', forbidden)
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: True)
    monkeypatch.setenv('SENTINEL_SESSION_TOKEN', 'readiness-test')
    response = TestClient(app).get('/api/workspace/readiness', headers={'X-Sentinel-Session': 'readiness-test'})
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['checks']] == IDS
