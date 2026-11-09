"""Explicit, local English document embeddings; vectors live only in SQLCipher."""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import threading
from sqlalchemy import text
from app.db.database import SessionLocal
from app.core.vault import vault

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / 'embedding-model.json').read_text(encoding='utf-8'))
MODEL = ROOT / 'models' / MANIFEST['filename']
MODEL_HASH = MANIFEST['sha256']
MAX_CHUNKS = 10000
_busy = threading.Lock()
_epoch = 0

SCHEMA = [
    'CREATE TABLE IF NOT EXISTS semantic_documents (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, model TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS semantic_chunks (document_id TEXT NOT NULL, ordinal INTEGER NOT NULL, excerpt TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY(document_id,ordinal))',
    """CREATE TRIGGER IF NOT EXISTS semantic_update AFTER UPDATE OF title,content,kind ON work_items BEGIN
       DELETE FROM semantic_chunks WHERE document_id=old.id;
       DELETE FROM semantic_documents WHERE id=old.id; END""",
    """CREATE TRIGGER IF NOT EXISTS semantic_delete AFTER DELETE ON work_items BEGIN
       DELETE FROM semantic_chunks WHERE document_id=old.id;
       DELETE FROM semantic_documents WHERE id=old.id; END""",
]


class SemanticError(ValueError):
    pass


def cancel(_reason='cancelled'):
    global _epoch
    _epoch += 1


vault.add_lock_listener(cancel)


def _check(epoch):
    from app.core.resource_governor import resource_governor, SystemState
    if epoch != _epoch or not vault.is_unlocked():
        raise SemanticError('Document search was interrupted. Unlock and try again.')
    if resource_governor.state not in (SystemState.IDLE, SystemState.INTERACTIVE):
        raise SemanticError('Document search is paused until the PC is available.')


def status():
    with SessionLocal() as db:
        total = db.execute(text("SELECT count(*) FROM work_items WHERE kind='document'")).scalar()
        indexed = db.execute(text('SELECT count(*) FROM semantic_documents WHERE model=:m'), {'m': MODEL_HASH}).scalar()
    return {'installed': MODEL.is_file(), 'documents': total, 'indexed': indexed,
            'pending': max(0, total-indexed), 'busy': _busy.locked(), 'language': 'English'}


def _load_model():
    try:
        if MODEL.stat().st_size != MANIFEST['size']:
            raise OSError()
        with MODEL.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != MODEL_HASH:
                raise OSError()
    except OSError:
        raise SemanticError('The local search model is missing or changed. Run the documented model setup.') from None
    from llama_cpp import Llama
    return Llama(model_path=str(MODEL), embedding=True, n_ctx=512, n_batch=512,
                 n_threads=2, n_gpu_layers=0, verbose=False)


@contextmanager
def _operation():
    if not _busy.acquire(blocking=False):
        raise SemanticError('Another document indexing or search operation is running.')
    epoch = _epoch
    model = None
    try:
        _check(epoch)
        model = _load_model()
        _check(epoch)
        yield model, epoch
    except SemanticError:
        raise
    except Exception:
        raise SemanticError('Local semantic search failed. Try keyword search or check the model setup.') from None
    finally:
        # No cached inference context retains document inputs after the request.
        del model
        _busy.release()


def _vector(model, value, epoch):
    _check(epoch)
    result = model.embed(value, normalize=True, truncate=False)
    _check(epoch)
    if len(result) != 384 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in result):
        raise SemanticError('The search model returned an invalid embedding.')
    norm = math.sqrt(sum(x*x for x in result))
    if norm == 0:
        raise SemanticError('The search model returned an empty embedding.')
    return [x/norm for x in result]


def fingerprint(title, content):
    return hashlib.sha256(json.dumps([title, content], ensure_ascii=False).encode()).hexdigest()


def index_next():
    """Index one document per owner request; edits during inference are discarded."""
    with _operation() as (model, epoch):
        with SessionLocal() as db:
            row = db.execute(text("""SELECT w.id,w.title,w.content FROM work_items w
                LEFT JOIN semantic_documents s ON s.id=w.id AND s.model=:m
                WHERE w.kind='document' AND s.id IS NULL ORDER BY w.created_at,w.id LIMIT 1"""), {'m': MODEL_HASH}).mappings().first()
        if row is None:
            return {'updated': False, **status()}
        ident, title, content = row['id'], row['title'], row['content'] or ''
        if len(content) > 60000 or len(title) > 160:
            raise SemanticError('This document exceeds the supported size. Shorten it before indexing.')
        # Overlap preserves short phrases at chunk boundaries; no silent model truncation.
        excerpts = [content[i:i+320] for i in range(0, len(content), 280)] or ['']
        vectors = [_vector(model, title[:100] + '\n' + excerpt, epoch) for excerpt in excerpts]
        _check(epoch)
        with SessionLocal() as db:
            # First write obtains SQLite's writer lock and compares the exact source.
            inserted = db.execute(text("""INSERT OR REPLACE INTO semantic_documents(id,fingerprint,model)
                SELECT id,:f,:m FROM work_items WHERE id=:id AND kind='document'
                AND title=:title AND coalesce(content,'')=:content"""),
                {'id': ident, 'f': fingerprint(title, content), 'm': MODEL_HASH, 'title': title, 'content': content})
            if inserted.rowcount != 1:
                raise SemanticError('The document changed while indexing. Try again.')
            db.execute(text('DELETE FROM semantic_chunks WHERE document_id=:id'), {'id': ident})
            count = db.execute(text('SELECT count(*) FROM semantic_chunks')).scalar()
            if count + len(excerpts) > MAX_CHUNKS:
                raise SemanticError('The local search index is full. Remove documents before indexing more.')
            for i, (excerpt, vector) in enumerate(zip(excerpts, vectors)):
                db.execute(text('INSERT INTO semantic_chunks VALUES (:id,:i,:e,:v)'),
                           {'id': ident, 'i': i, 'e': excerpt, 'v': json.dumps(vector)})
            _check(epoch)
            db.commit()
        return {'updated': True, **status()}


def search(query, limit=5):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300:
        raise SemanticError('Enter 1 to 300 characters to search.')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise SemanticError('Choose 1 to 20 results.')
    with _operation() as (model, epoch):
        vector = _vector(model, 'Represent this sentence for searching relevant passages: ' + query, epoch)
        best = {}
        with SessionLocal() as db:
            rows = db.execute(text("""SELECT c.document_id,c.excerpt,c.vector,s.fingerprint,w.title
                FROM semantic_chunks c JOIN semantic_documents s ON s.id=c.document_id
                JOIN work_items w ON w.id=s.id WHERE s.model=:m AND w.kind='document'
                LIMIT :cap"""), {'m': MODEL_HASH, 'cap': MAX_CHUNKS+1}).mappings()
            for n, row in enumerate(rows):
                if n >= MAX_CHUNKS:
                    raise SemanticError('The search index exceeds its size limit.')
                values = json.loads(row['vector'])
                if len(values) != len(vector) or not all(isinstance(x, (int,float)) and math.isfinite(x) for x in values):
                    raise SemanticError('The search index contains an invalid vector. Rebuild the document.')
                score = sum(a*b for a,b in zip(vector,values))
                ident = row['document_id']
                if ident not in best or score > best[ident]['score']:
                    best[ident] = {'id': ident, 'title': row['title'], 'excerpt': row['excerpt'],
                                   'score': round(score, 4), 'fingerprint': row['fingerprint']}
        _check(epoch)
        # Verify sources again so an edit/delete during ranking never yields stale text.
        result = []
        with SessionLocal() as db:
            for item in sorted(best.values(), key=lambda x: (-x['score'], x['id'])):
                row = db.execute(text("SELECT title,content FROM work_items WHERE id=:id AND kind='document'"), {'id': item['id']}).first()
                if row and fingerprint(row.title, row.content or '') == item.pop('fingerprint'):
                    result.append(item)
                if len(result) >= limit:
                    break
        _check(epoch)
        return result
