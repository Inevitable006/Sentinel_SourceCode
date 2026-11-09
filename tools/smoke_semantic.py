"""Synthetic native embedding check, offline and isolated from owner storage."""
import os
from pathlib import Path
import socket
import sys
import tempfile
import argparse


def blocked(*args, **kwargs):
    raise RuntimeError('Network forbidden during semantic smoke test')


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', type=Path, default=root / 'backend')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='sentinel_semantic_smoke_') as folder:
        os.environ['APPDATA'] = folder
        sys.path.insert(0, str(args.backend.resolve()))
        socket.socket.connect = blocked
        socket.socket.connect_ex = blocked
        socket.create_connection = blocked
        socket.getaddrinfo = blocked
        from app.core.semantic_search import _load_model
        model = _load_model()
        vectors = model.embed([
            'Represent this sentence for searching relevant passages: automobile repair',
            'Fixing a car engine',
            'Making a chocolate cake',
        ], normalize=True, truncate=False)
        assert all(len(v) == 384 for v in vectors)
        relevant, unrelated = [sum(a*b for a,b in zip(vectors[0], v)) for v in vectors[1:]]
        assert relevant > unrelated + 0.2, (relevant, unrelated)
        print(f'PASS: 384-dimensional local embeddings; relevant={relevant:.3f}, unrelated={unrelated:.3f}; network blocked.')
        del model
        from app.core import semantic_search
        from app.core.paths import ensure_paths
        from app.db import database
        from app.db.models import WorkItem
        ensure_paths()
        database.open_database(os.urandom(32))
        try:
            database.init_db()
            semantic_search.vault.is_unlocked = database.is_open
            with database.SessionLocal() as db:
                db.add_all([
                    WorkItem(id='synthetic-car', kind='document', title='Workshop', content='Fixing a car engine'),
                    WorkItem(id='synthetic-cake', kind='document', title='Kitchen', content='Making a chocolate cake'),
                ])
                db.commit()
            semantic_search.index_next()
            semantic_search.index_next()
            hits = semantic_search.search('automobile repair')
            assert hits[0]['id'] == 'synthetic-car', hits
            assert semantic_search.status()['indexed'] == 2
            assert b'Fixing a car engine' not in database.ENCRYPTED_DB_PATH.read_bytes()
            with database.SessionLocal() as db:
                db.delete(db.get(WorkItem, 'synthetic-car')); db.commit()
            assert all(r['id'] != 'synthetic-car' for r in semantic_search.search('automobile repair'))
            database.close_database()
            try:
                semantic_search.search('automobile repair')
            except semantic_search.SemanticError:
                pass
            else:
                raise AssertionError('Locked search must fail')
            print('PASS: real model + encrypted index + ranking + deletion + locked access; synthetic data only.')
        finally:
            database.close_database()


if __name__ == '__main__':
    main()
