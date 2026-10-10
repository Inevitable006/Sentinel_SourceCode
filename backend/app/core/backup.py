"""Encrypted backup and restore.

A backup (.sentinelbak) is a zip with:
  sentinel.db    a consistent copy of the encrypted database (SQLCipher VACUUM INTO, still encrypted)
  keystore.json  the wrapped keys (no key in the clear)
  manifest.json  version, date and SHA-256 of both files
Nothing in the file opens your data without your PIN (on this Windows account) or your recovery
key (anywhere). Restore first proves the PIN/recovery key opens the backup, keeps the current data
in backups/pre-restore-<time>/, and only then swaps the files in. Sentinel must be locked to restore.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app.core.paths import SENTINEL_DATA_DIR

BACKUP_DIR = SENTINEL_DATA_DIR / "backups"
SUFFIX = ".sentinelbak"
FORMAT_VERSION = 1
KEEP_LOCAL = 5
MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024
_failures: List[float] = []
_lock = threading.Lock()


class BackupError(Exception):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup() -> Path:
    """Sentinel must be unlocked (the copy is made through the open, keyed database)."""
    from app.core.vault import vault
    from app.db import database
    if not vault.is_unlocked():
        raise BackupError("Unlock Sentinel first.")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with _lock, tempfile.TemporaryDirectory(dir=BACKUP_DIR) as tmp:
        copy = Path(tmp) / "sentinel.db"
        with database.get_engine().connect() as conn:
            conn.exec_driver_sql("VACUUM INTO '%s'" % str(copy).replace("'", "''"))
        db_bytes = copy.read_bytes()
        keystore = json.dumps(vault._read(), indent=2).encode("utf-8")
        manifest = {"format": FORMAT_VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                    "files": {"sentinel.db": _sha256(db_bytes), "keystore.json": _sha256(keystore)}}
        name = f"sentinel-backup-{datetime.now():%Y%m%d-%H%M%S}{SUFFIX}"
        target = BACKUP_DIR / name
        with zipfile.ZipFile(target.with_suffix(".tmp"), "w", zipfile.ZIP_STORED) as z:   # already encrypted
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr("keystore.json", keystore)
            z.writestr("sentinel.db", db_bytes)
        os.replace(target.with_suffix(".tmp"), target)
    _prune()
    return target


def _prune():
    files = sorted(BACKUP_DIR.glob(f"*{SUFFIX}"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP_LOCAL:]:
        old.unlink(missing_ok=True)


def list_backups() -> List[Dict]:
    if not BACKUP_DIR.exists():
        return []
    return [{"name": p.name, "size": p.stat().st_size,
             "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(BACKUP_DIR.glob(f"*{SUFFIX}"), key=lambda p: p.stat().st_mtime, reverse=True)]


def backup_path(name: str) -> Path:
    path = (BACKUP_DIR / name).resolve()
    if path.parent != BACKUP_DIR.resolve() or not name.endswith(SUFFIX) or not path.is_file():
        raise BackupError("Backup not found.")
    return path


def _read_archive(data: bytes) -> Dict[str, bytes]:
    if len(data) > MAX_BACKUP_BYTES:
        raise BackupError("The file is too large to be a Sentinel backup.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            if names != {"manifest.json", "keystore.json", "sentinel.db"}:
                raise BackupError("This is not a Sentinel backup file.")
            files = {n: z.read(n) for n in names}
    except zipfile.BadZipFile:
        raise BackupError("This is not a Sentinel backup file.") from None
    try:
        manifest = json.loads(files["manifest.json"])
    except ValueError:
        raise BackupError("The backup's manifest is damaged.") from None
    if manifest.get("format") != FORMAT_VERSION:
        raise BackupError("This backup was made by an unsupported Sentinel version.")
    for name in ("sentinel.db", "keystore.json"):
        if manifest.get("files", {}).get(name) != _sha256(files[name]):
            raise BackupError(f"The backup is damaged or was changed ({name} does not match its checksum).")
    return files


def _rate_limit():
    now = time.time()
    _failures[:] = [t for t in _failures if now - t < 300]
    if len(_failures) >= 5:
        raise BackupError("Too many wrong attempts. Wait a few minutes and try again.")


def verify_backup(data: bytes, secret: str, kind: str) -> Dict:
    """Proves the PIN/recovery key opens this backup's data. Returns its manifest + table counts."""
    from sqlalchemy import create_engine, text
    from app.core import vault as vault_mod
    from app.db import database
    files = _read_archive(data)
    ks = json.loads(files["keystore.json"])
    _rate_limit()
    try:
        if kind == "recovery":
            dek = vault_mod.vault._unwrap_recovery(ks, vault_mod.parse_recovery_key(secret))
        elif kind == "pin":
            dek = vault_mod.vault._unwrap_pin(ks, vault_mod._pin_bytes(secret, for_new_pin=False))
        else:
            raise BackupError("Choose PIN or recovery key.")
    except vault_mod.WrongSecret as e:
        _failures.append(time.time())
        raise BackupError(str(e)) from None
    except vault_mod.VaultError as e:
        raise BackupError(str(e)) from None
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "check.db"
        db_file.write_bytes(files["sentinel.db"])
        engine = create_engine(database._url(db_file, dek))
        try:
            with engine.connect() as conn:
                tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
                counts = {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
                          for t in ("threads", "memory_items", "work_items", "portfolio_holdings") if t in tables}
                check = conn.execute(text("PRAGMA quick_check")).scalar()
        except Exception:
            raise BackupError("The backup's database could not be opened with that key.") from None
        finally:
            engine.dispose()
    if check != "ok":
        raise BackupError("The backup's database is damaged.")
    return {"manifest": json.loads(files["manifest.json"]), "counts": counts}


def restore_backup(data: bytes, secret: str, kind: str) -> Dict:
    from app.core.vault import vault
    from app.db import database
    if vault.is_unlocked():
        raise BackupError("Lock Sentinel before restoring a backup.")
    info = verify_backup(data, secret, kind)
    files = _read_archive(data)
    with _lock:
        aside = BACKUP_DIR / f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}"
        aside.mkdir(parents=True, exist_ok=True)
        db_path = database.ENCRYPTED_DB_PATH
        targets = [db_path, vault._path, vault._backup_path]
        for path in targets:
            if path.exists():
                shutil.copy2(path, aside / path.name)
        tmp_db = db_path.with_suffix(".restore-tmp")
        tmp_db.write_bytes(files["sentinel.db"])
        for extra in (db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
            extra.unlink(missing_ok=True)
        os.replace(tmp_db, db_path)
        for path in (vault._path, vault._backup_path):
            tmp = path.with_suffix(".restore-tmp")
            tmp.write_bytes(files["keystore.json"])
            os.replace(tmp, path)
    return {**info, "previous_data_kept_in": str(aside),
            "next": ("Unlock with your PIN." if kind == "pin"
                     else "Use 'Forgot PIN' with the same recovery key to set a PIN on this PC.")}
