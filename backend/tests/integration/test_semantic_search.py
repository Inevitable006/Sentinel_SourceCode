"""Encrypted semantic index lifecycle without downloading or loading a model."""
import json
import uuid
import pytest
from sqlalchemy import text
from app.core import semantic_search as search
from app.db.database import SessionLocal, ENCRYPTED_DB_PATH
from app.db.models import WorkItem


class Model:
    def embed(self, value, **kwargs):
        # Deterministic stand-in: native model quality has a separate offline smoke.
        assert kwargs == {'normalize': True, 'truncate': False}
        return ([1., 0.] if 'car' in value else [0., 1.]) + [0.] * 382


@pytest.fixture
def corpus(monkeypatch):
    from app.core.resource_governor import resource_governor, SystemState
    monkeypatch.setattr(resource_governor, 'state', SystemState.IDLE)
    monkeypatch.setattr(search.vault, 'is_unlocked', lambda: True)
    monkeypatch.setattr(search, '_load_model', Model)
    with SessionLocal() as db:
        db.query(WorkItem).filter_by(kind='document').delete(); db.commit()
    ids = []
    def add(content='car repairs', title='Notes'):
        ident = str(uuid.uuid4()); ids.append(ident)
        with SessionLocal() as db:
            db.add(WorkItem(id=ident, kind='document', title=title, content=content)); db.commit()
        return ident
    yield add
    with SessionLocal() as db:
        for ident in ids:
            db.query(WorkItem).filter_by(id=ident).delete()
        db.commit()


def test_index_search_and_encrypted_storage(corpus):
    ident = corpus()
    assert search.status()['pending'] == 1
    assert search.index_next()['indexed'] == 1
    result = search.search('car')
    assert result[0]['id'] == ident and result[0]['score'] == 1
    assert 'car repairs' == result[0]['excerpt']
    assert b'car repairs' not in ENCRYPTED_DB_PATH.read_bytes()
    assert search.status()['pending'] == 0


def test_edit_delete_and_kind_changes_invalidate_vectors(corpus):
    ident = corpus(); search.index_next()
    with SessionLocal() as db:
        row = db.get(WorkItem, ident); row.content = 'cake'; db.commit()
    assert search.search('car') == [] and search.status()['pending'] == 1
    search.index_next()
    with SessionLocal() as db:
        row = db.get(WorkItem, ident); row.kind = 'email_draft'; db.commit()
        assert db.execute(text('SELECT count(*) FROM semantic_chunks WHERE document_id=:id'), {'id': ident}).scalar() == 0
        row.kind = 'document'; db.commit()
    search.index_next()
    with SessionLocal() as db:
        db.delete(db.get(WorkItem, ident)); db.commit()
    assert search.search('cake') == []


def test_edit_during_inference_does_not_commit_stale_chunks(corpus, monkeypatch):
    ident = corpus()
    class EditingModel(Model):
        def embed(self, *args, **kwargs):
            with SessionLocal() as db:
                db.get(WorkItem, ident).content = 'changed'; db.commit()
            return super().embed(*args, **kwargs)
    monkeypatch.setattr(search, '_load_model', EditingModel)
    with pytest.raises(search.SemanticError, match='changed'): search.index_next()
    assert search.status()['pending'] == 1


def test_cancel_during_inference_discards_results(corpus, monkeypatch):
    corpus()
    class CancellingModel(Model):
        def embed(self, *args, **kwargs):
            search.cancel()
            return super().embed(*args, **kwargs)
    monkeypatch.setattr(search, '_load_model', CancellingModel)
    with pytest.raises(search.SemanticError, match='interrupted'): search.index_next()
    assert search.status()['pending'] == 1 and not search._busy.locked()


def test_paused_locked_and_busy_fail_before_model_load(corpus, monkeypatch):
    from app.core.resource_governor import resource_governor, SystemState
    monkeypatch.setattr(search, '_load_model', lambda: pytest.fail('Must not load'))
    monkeypatch.setattr(resource_governor, 'state', SystemState.USER_PAUSED)
    with pytest.raises(search.SemanticError, match='paused'): search.search('car')
    monkeypatch.setattr(resource_governor, 'state', SystemState.IDLE)
    monkeypatch.setattr(search.vault, 'is_unlocked', lambda: False)
    with pytest.raises(search.SemanticError, match='interrupted'): search.index_next()
    search._busy.acquire()
    try:
        with pytest.raises(search.SemanticError, match='running'): search.search('car')
    finally: search._busy.release()


def test_invalid_vector_and_capacity_roll_back(corpus, monkeypatch):
    corpus()
    monkeypatch.setattr(search, 'MAX_CHUNKS', 0)
    with pytest.raises(search.SemanticError, match='full'): search.index_next()
    assert search.status()['pending'] == 1
    monkeypatch.setattr(search, 'MAX_CHUNKS', 10000)
    monkeypatch.setattr(Model, 'embed', lambda *a, **kw: [float('nan')] * 384)
    with pytest.raises(search.SemanticError, match='invalid'): search.index_next()
    assert search.status()['pending'] == 1


def test_model_change_requires_reindex_and_query_bounds(corpus, monkeypatch):
    corpus(); search.index_next()
    monkeypatch.setattr(search, 'MODEL_HASH', 'another-model')
    assert search.status()['pending'] == 1 and search.search('car') == []
    search.index_next()
    assert search.status()['pending'] == 0
    for query in ('', 'x' * 301):
        with pytest.raises(search.SemanticError): search.search(query)
    with pytest.raises(search.SemanticError): search.search('car', limit=21)


def test_routes_reject_unauthorized_and_locked(corpus, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv('SENTINEL_SESSION_TOKEN', 'semantic-test')
    client = TestClient(app); headers = {'X-Sentinel-Session': 'semantic-test'}
    corpus()
    assert client.post('/api/workspace/documents-index/next').status_code == 422
    assert client.get('/api/workspace/documents-index/status', headers=headers).status_code == 200
    assert client.post('/api/workspace/documents-index/next', headers=headers).status_code == 200
    assert client.post('/api/workspace/documents/search', headers=headers, json={'query':'car','mode':'semantic'}).json()
    monkeypatch.setattr(search.vault, 'is_unlocked', lambda: False)
    assert client.post('/api/workspace/documents-index/next', headers=headers).status_code == 423
    assert client.post('/api/workspace/documents/search', headers=headers, json={'query':'car','mode':'semantic'}).status_code == 423
