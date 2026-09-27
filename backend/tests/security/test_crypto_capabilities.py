"""
The crypto building blocks the owner unlock and encrypted database rely on actually work
on this machine's Python (Phase 1, steps 1.3/1.4). If one of these fails, stop and fix it
before trusting anything built on top.
"""
import os
import sys

import pytest


def test_argon2id_available():
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    k1 = Argon2id(salt=b"s" * 16, length=32, iterations=1, lanes=1, memory_cost=8192).derive(b"123456")
    k2 = Argon2id(salt=b"s" * 16, length=32, iterations=1, lanes=1, memory_cost=8192).derive(b"123456")
    k3 = Argon2id(salt=b"t" * 16, length=32, iterations=1, lanes=1, memory_cost=8192).derive(b"123456")
    assert len(k1) == 32 and k1 == k2 and k1 != k3


def test_aes_gcm_detects_tampering():
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key, nonce = AESGCM.generate_key(256), os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, b"secret", b"aad")
    assert AESGCM(key).decrypt(nonce, ct, b"aad") == b"secret"
    bad = bytes([ct[0] ^ 1]) + ct[1:]
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(nonce, bad, b"aad")


def test_sqlcipher_raw_key_fts5_and_export(tmp_path):
    import sqlite3
    import sqlcipher3.dbapi2 as sq
    key = os.urandom(32).hex()
    # a plaintext database, like the old jarvis_memory.db
    plain = tmp_path / "plain.db"
    c = sqlite3.connect(plain)
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    c.executemany("INSERT INTO t (v) VALUES (?)", [("alpha",), ("beta",)])
    c.commit(); c.close()
    # sqlcipher_export into an encrypted copy
    enc = tmp_path / "enc.db"
    c = sq.connect(str(plain))
    c.execute(f"ATTACH DATABASE ? AS enc KEY \"x'{key}'\"", (str(enc),))
    c.execute("SELECT sqlcipher_export('enc')")
    c.execute("DETACH DATABASE enc")
    c.close()
    # the encrypted file has no readable header or plaintext
    raw = enc.read_bytes()
    assert not raw.startswith(b"SQLite format 3") and b"alpha" not in raw
    # opens with the key; FTS5 works; plain sqlite3 can't read it
    c = sq.connect(str(enc))
    c.execute(f"PRAGMA key = \"x'{key}'\"")
    assert [r[0] for r in c.execute("SELECT v FROM t ORDER BY id")] == ["alpha", "beta"]
    c.execute("CREATE VIRTUAL TABLE f USING fts5(content)")
    c.execute("INSERT INTO f(content) VALUES ('remember the blue notebook')")
    assert c.execute("SELECT count(*) FROM f WHERE f MATCH 'notebook'").fetchone()[0] == 1
    assert c.execute("PRAGMA cipher_integrity_check").fetchall() == []
    c.commit(); c.close()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(enc).execute("SELECT * FROM t").fetchall()
    # wrong key fails on first read
    c = sq.connect(str(enc))
    c.execute(f"PRAGMA key = \"x'{os.urandom(32).hex()}'\"")
    with pytest.raises(sq.DatabaseError):
        c.execute("SELECT count(*) FROM sqlite_master").fetchone()
    c.close()


def test_sqlalchemy_pysqlcipher_dialect(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    key = os.urandom(32).hex()
    eng = create_engine(URL.create("sqlite+pysqlcipher", password=f"x'{key}'", database=str(tmp_path / "a.db")))
    with eng.begin() as c:
        c.execute(text("CREATE TABLE t (v TEXT)"))
        c.execute(text("INSERT INTO t VALUES ('ok')"))
    with eng.connect() as c:
        assert c.execute(text("SELECT v FROM t")).scalar() == "ok"
    assert key not in repr(eng.url) and key not in str(eng.url)   # key never shown in logs/reprs
    eng.dispose()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_round_trip():
    from app.core.dpapi import protect, unprotect
    blob = protect(b"data key", entropy=b"sentinel")
    assert blob != b"data key" and unprotect(blob, entropy=b"sentinel") == b"data key"
    with pytest.raises(OSError):
        unprotect(blob, entropy=b"wrong")
