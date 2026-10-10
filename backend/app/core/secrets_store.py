"""
Secrets vault: API keys, tokens and passwords that skills may need (for example a calendar or
email integration later). Values live only inside the encrypted database, are never sent back to
the UI after they are saved, and are masked in every log line (app.core.redaction).
"""
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import text

from app.core import redaction
from app.db.database import get_engine

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_VALUE_LEN = 8192


class SecretError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SecretError("Use 1-64 letters, digits, '.', '_' or '-' for the name.")
    return name


def set_secret(name: str, value: str) -> None:
    _check_name(name)
    if not isinstance(value, str) or not value or len(value) > MAX_VALUE_LEN:
        raise SecretError(f"The value must be 1-{MAX_VALUE_LEN} characters.")
    now = _now()
    with get_engine().begin() as conn:
        conn.execute(text("""INSERT INTO secrets (name, value, created_at, updated_at) VALUES (:n, :v, :t, :t)
                             ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"""),
                     {"n": name, "v": value, "t": now})
    redaction.register(value)


def get_secret(name: str) -> Optional[str]:
    """For backend code only (skills); never exposed through the API."""
    _check_name(name)
    with get_engine().connect() as conn:
        value = conn.execute(text("SELECT value FROM secrets WHERE name = :n"), {"n": name}).scalar()
    if value:
        redaction.register(value)
    return value


def list_secrets() -> List[Dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT name, created_at, updated_at FROM secrets ORDER BY name")).fetchall()
    return [{"name": r[0], "created_at": r[1], "updated_at": r[2]} for r in rows]


def delete_secret(name: str) -> bool:
    _check_name(name)
    with get_engine().begin() as conn:
        value = conn.execute(text("SELECT value FROM secrets WHERE name = :n"), {"n": name}).scalar()
        conn.execute(text("PRAGMA secure_delete = ON"))
        deleted = conn.execute(text("DELETE FROM secrets WHERE name = :n"), {"n": name}).rowcount
    if value:
        redaction.unregister(value)
    return bool(deleted)


def register_all_for_redaction() -> int:
    """At unlock: make sure no stored secret can ever appear in a log line."""
    with get_engine().connect() as conn:
        values = [r[0] for r in conn.execute(text("SELECT value FROM secrets"))]
    redaction.register_many(values)
    return len(values)
