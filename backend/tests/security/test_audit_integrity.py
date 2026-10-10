"""F19: audit lines carry no secrets or paths; tampering is detectable; the log is bounded."""
import json

import pytest

from app.core import audit_logger as audit_module, redaction
from app.core.audit_logger import AuditLogger


@pytest.fixture
def log(tmp_path):
    return AuditLogger(tmp_path / "audit.log", tmp_path / "audit.key")


def lines(logger):
    return [json.loads(l) for l in logger.log_file.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_sensitive_error_text_does_not_reach_the_log(log):
    redaction.register("hunter2-super-secret")
    try:
        log.log_event("execution_failed", {"tool_name": "t", "error": r"cannot open C:\Users\owner\Documents\diary.txt with hunter2-super-secret",
                                           "args": {"query": "my diagnosis"}, "message": "/home/owner/private/file"})
    finally:
        redaction.unregister("hunter2-super-secret")
    raw = log.log_file.read_text(encoding="utf-8")
    for leaked in ("diary.txt", "hunter2-super-secret", "my diagnosis", "/home/owner", r"C:\\Users"):
        assert leaked not in raw, leaked
    assert "<path>" in raw


def test_untouched_log_verifies(log):
    for i in range(5):
        log.log_event("e", {"i": i})
    assert log.verify_log() == {"ok": True, "entries": 5, "problem": None}


@pytest.mark.parametrize("tamper", ["edit", "remove_middle", "reorder", "remove_last"])
def test_tampering_is_detected(log, tamper):
    for i in range(5):
        log.log_event("e", {"i": i})
    raw = log.log_file.read_text(encoding="utf-8").splitlines()
    if tamper == "edit":
        raw[2] = raw[2].replace('"i": 2', '"i": 99')
    elif tamper == "remove_middle":
        del raw[2]
    elif tamper == "reorder":
        raw[1], raw[2] = raw[2], raw[1]
    else:
        del raw[-1]
    log.log_file.write_text("\n".join(raw) + "\n", encoding="utf-8")
    result = log.verify_log()
    assert result["ok"] is False and result["problem"]


def test_chain_survives_restart_and_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_module, "MAX_BYTES", 600)
    first = AuditLogger(tmp_path / "audit.log", tmp_path / "audit.key")
    for i in range(10):
        first.log_event("e", {"i": i})
    again = AuditLogger(tmp_path / "audit.log", tmp_path / "audit.key")   # e.g. after a restart
    for i in range(10, 20):
        again.log_event("e", {"i": i})
    assert (tmp_path / "audit.1.log").exists()
    assert not (tmp_path / f"audit.{audit_module.KEEP_ROTATED + 1}.log").exists()
    result = again.verify_log()
    assert result["ok"], result


def test_key_is_protected_at_rest(log):
    log.log_event("e", {})
    from app.core import dpapi
    if dpapi.available():
        assert len(log.key_file.read_bytes()) > 32   # a DPAPI blob, not the raw 32-byte key


def test_unchained_legacy_log_is_set_aside(tmp_path):
    (tmp_path / "audit.log").write_text('{"timestamp": 1, "event_type": "old", "details": {}}\n')
    log = AuditLogger(tmp_path / "audit.log", tmp_path / "audit.key")
    log.log_event("new", {})
    assert list(tmp_path.glob("audit.unchained-*.log"))
    assert log.verify_log()["ok"]


def test_lock_clears_plaintext_secret_copies():
    redaction.register("value-to-forget-123")
    from app.main import app  # noqa: F401  registers the lock listener
    from app.core.vault import vault
    assert redaction.clear_registered in vault._listeners
    redaction.clear_registered("locked")
    assert redaction.redact("value-to-forget-123") == "value-to-forget-123"
