"""Real encrypted index lifecycle; all fixtures use throwaway owner storage."""
import uuid
import pytest
from sqlalchemy import text
from app.db.database import SessionLocal, init_db, ENCRYPTED_DB_PATH, DatabaseLocked
from app.db.models import WorkItem
from app.core.document_search import search_documents


@pytest.fixture
def docs():
    ids = []
    def add(title, content, kind="document"):
        ident = str(uuid.uuid4()); ids.append(ident)
        with SessionLocal() as db:
            db.add(WorkItem(id=ident, kind=kind, title=title, content=content))
            db.commit()
        return ident
    yield add
    with SessionLocal() as db:
        for ident in ids:
            db.query(WorkItem).filter_by(id=ident).delete()
        db.commit()


def test_index_ranks_title_and_excludes_other_private_records(docs):
    title = docs("orchidquartz", "A short entry")
    body = docs("Other", "A short orchidquartz entry")
    docs("orchidquartz", "Hidden email", "email_draft")
    with SessionLocal() as db:
        results = search_documents(db, "orchidquartz")
        assert [r['id'] for r in results] == [title, body]
        assert "Hidden email" not in str(results)


def test_edit_delete_and_kind_change_update_index(docs):
    ident = docs("Lifecycle", "oldquartz")
    with SessionLocal() as db:
        row = db.get(WorkItem, ident); row.content = "newquartz"; db.commit()
        assert search_documents(db, "oldquartz") == []
        assert search_documents(db, "newquartz")[0]['id'] == ident
        row.kind = "email_draft"; db.commit()
        assert search_documents(db, "newquartz") == []
        row.kind = "document"; db.commit()
        assert search_documents(db, "newquartz")
        db.delete(row); db.commit()
        assert search_documents(db, "newquartz") == []


def test_backfill_is_idempotent_and_index_is_encrypted(docs):
    marker = "privatecanaryquartz" + uuid.uuid4().hex
    ident = docs("Backfill", marker)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM fts_documents WHERE id=:id"), {'id': ident}); db.commit()
        assert search_documents(db, marker) == []
    init_db(); init_db()
    with SessionLocal() as db:
        assert len(search_documents(db, marker)) == 1
    assert marker.encode() not in ENCRYPTED_DB_PATH.read_bytes()


def test_literals_unicode_and_limits(docs):
    docs("Unicode", "café naïve orchidquartz")
    with SessionLocal() as db:
        assert len(search_documents(db, '"café" naïve')) == 1
        assert search_documents(db, 'orchidquartz OR missingquartz') == []
        assert search_documents(db, '"*()') == []
        for query in (' ', 'a' * 301, ' '.join(f'word{i}' for i in range(21))):
            with pytest.raises(ValueError): search_documents(db, query)
        with pytest.raises(ValueError): search_documents(db, 'café', limit=100)


def test_bounded_excerpts_and_results(docs):
    for i in range(7): docs(f"Bound {i}", "boundedquartz " + 'a' * 5000)
    with SessionLocal() as db:
        results = search_documents(db, 'boundedquartz')
        assert len(results) == 5
        assert all(len(r['excerpt']) <= 1200 for r in results)


def test_locked_database_refuses_search(locked_db):
    from skills.document_analysis import search_saved_documents
    with pytest.raises(DatabaseLocked): search_saved_documents('private')


def test_failed_edit_rolls_back_index_with_document(docs):
    ident = docs('Rollback', 'originalquartz')
    with SessionLocal() as db:
        db.get(WorkItem, ident).content = 'uncommittedquartz'
        db.flush()
        assert search_documents(db, 'uncommittedquartz')
        db.rollback()
        assert search_documents(db, 'uncommittedquartz') == []
        assert search_documents(db, 'originalquartz')[0]['id'] == ident


def test_routes_require_owner_and_open_only_documents(docs, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import workspace_routes as ws
    monkeypatch.setenv('SENTINEL_SESSION_TOKEN', 'document-test-token')
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: True)
    client = TestClient(app); headers = {'X-Sentinel-Session': 'document-test-token'}
    ident = docs('API', 'routequartz')
    draft = docs('Private draft', 'routequartz', 'email_draft')
    url = '/api/workspace/documents/search'
    assert client.post(url, json={'query': 'routequartz'}).status_code == 422
    assert client.post(url, headers=headers, json={'query': 'routequartz'}).json()[0]['id'] == ident
    assert client.get(f'/api/workspace/documents/{ident}', headers=headers).json()['content'] == 'routequartz'
    assert client.get(f'/api/workspace/documents/{draft}', headers=headers).status_code == 404
    monkeypatch.setattr(ws.vault, 'is_unlocked', lambda: False)
    assert client.post(url, headers=headers, json={'query': 'routequartz'}).status_code == 423
    assert client.get(f'/api/workspace/documents/{ident}', headers=headers).status_code == 423


def test_skill_keeps_confirmation_and_source_notice(docs, monkeypatch):
    from app.core.skill_loader import register_all_skills
    from app.core.policy_engine import policy_engine, PolicyDecision
    from skills.document_analysis import search_saved_documents
    from app.core.resource_governor import resource_governor, SystemState
    monkeypatch.setattr(resource_governor, 'state', SystemState.IDLE)
    register_all_skills()
    decision, _ = policy_engine.evaluate('skill_search_saved_documents', {'query': 'skillquartz'}, 'test')
    assert decision == PolicyDecision.NEEDS_CONFIRMATION
    ident = docs('Source', 'skillquartz')
    result = search_saved_documents('skillquartz')
    assert ident in result and 'Untrusted document excerpts' in result
