"""Encrypted backup/restore with a real vault and a real SQLCipher database (temporary folder)."""
import io
import json
import zipfile

import pytest
from sqlalchemy import text

from app.core import backup, vault as vmod
from app.db import database

PIN = "blue-482915"


@pytest.fixture
def env(tmp_path, monkeypatch, reopen_db):
    monkeypatch.setattr(vmod, "KDF_PARAMS", {"iterations": 1, "lanes": 1, "memory_cost": 8192})
    db_path = tmp_path / "sentinel.db"

    def opener(key, first_setup, **_):
        database.open_database(key, db_path)
        database.init_db()
        return {}

    v = vmod.Vault(keystore_path=tmp_path / "keystore.json", db_opener=opener, db_closer=database.close_database)
    monkeypatch.setattr(vmod, "vault", v)
    monkeypatch.setattr(database, "ENCRYPTED_DB_PATH", db_path)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    backup._failures.clear()
    recovery = v.setup(PIN)["recovery_key"]
    return v, recovery, db_path, tmp_path


def remember(text_value):
    with database.get_engine().begin() as conn:
        conn.execute(text("INSERT INTO memory_items(id, content) VALUES(:i, :c)"), {"i": text_value, "c": text_value})


def memories():
    with database.get_engine().connect() as conn:
        return sorted(r[0] for r in conn.execute(text("SELECT content FROM memory_items")))


def test_backup_is_encrypted_and_verifiable(env):
    v, recovery, _, _ = env
    remember("my private note")
    path = backup.create_backup()
    raw = path.read_bytes()
    assert b"my private note" not in raw and b"SQLite format 3" not in raw
    data = path.read_bytes()
    assert backup.verify_backup(data, PIN, "pin")["counts"]["memory_items"] == 1
    assert backup.verify_backup(data, recovery, "recovery")["counts"]["memory_items"] == 1
    with pytest.raises(backup.BackupError, match="Wrong PIN"):
        backup.verify_backup(data, "wrong-pin-123", "pin")


def test_restore_round_trip_keeps_previous_data_aside(env):
    v, recovery, db_path, tmp = env
    remember("before backup")
    data = backup.create_backup().read_bytes()
    remember("after backup")
    with pytest.raises(backup.BackupError, match="Lock Sentinel"):
        backup.restore_backup(data, recovery, "recovery")
    v.lock("test")
    result = backup.restore_backup(data, recovery, "recovery")
    v.unlock(PIN)
    assert memories() == ["before backup"]
    aside = list((tmp / "backups").glob("pre-restore-*"))
    assert aside and (aside[0] / "sentinel.db").exists() and (aside[0] / "keystore.json").exists()
    assert "Forgot PIN" in result["next"]


def test_damaged_or_foreign_files_are_refused(env):
    data = backup.create_backup().read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    db = bytearray(files["sentinel.db"]); db[5000] ^= 0xFF
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in {**files, "sentinel.db": bytes(db)}.items():
            z.writestr(n, b)
    with pytest.raises(backup.BackupError, match="damaged or was changed"):
        backup.verify_backup(buf.getvalue(), PIN, "pin")
    with pytest.raises(backup.BackupError, match="not a Sentinel backup"):
        backup.verify_backup(b"hello", PIN, "pin")


def test_wrong_attempts_are_rate_limited(env):
    data = backup.create_backup().read_bytes()
    for _ in range(5):
        with pytest.raises(backup.BackupError):
            backup.verify_backup(data, "wrong-pin-123", "pin")
    with pytest.raises(backup.BackupError, match="Too many"):
        backup.verify_backup(data, PIN, "pin")


def test_only_recent_backups_are_kept_locally(env, monkeypatch):
    monkeypatch.setattr(backup, "KEEP_LOCAL", 2)
    import time
    for _ in range(3):
        backup.create_backup(); time.sleep(1.1)
    assert len(backup.list_backups()) == 2
    with pytest.raises(backup.BackupError):
        backup.backup_path("..\\keystore.json")
