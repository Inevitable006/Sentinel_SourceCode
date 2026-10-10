"""Append-only audit log with tamper detection.

Policy:
- Tool arguments are logged by name/type/length only; sensitive keys are redacted; error text is
  shortened and local paths are removed; the finished line passes through the secret redactor.
- Every entry carries an HMAC chained to the previous entry ("mac"). Editing, removing or
  reordering entries breaks the chain; verify_log() reports where. The HMAC key is random and
  protected with Windows DPAPI (bound to this Windows account), so the chain cannot be rebuilt
  by someone who only has a copy of the files. Someone running as the same Windows user could
  still rewrite the whole log and key: this detects tampering, it cannot prevent it.
- The log rotates at MAX_BYTES, keeping KEEP_ROTATED older files; the chain continues across files.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from app.core.paths import SENTINEL_DATA_DIR

AUDIT_LOG_FILE = SENTINEL_DATA_DIR / "audit.log"
AUDIT_KEY_FILE = SENTINEL_DATA_DIR / "audit.key"
MAX_BYTES = 5 * 1024 * 1024
KEEP_ROTATED = 3
GENESIS = "0" * 64

_PATH = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s\"'<>|]*|(?:/[\w.\-]+){2,}")


def _load_key(key_file: Path) -> bytes:
    from app.core import dpapi
    try:
        blob = key_file.read_bytes()
        return dpapi.unprotect(blob) if dpapi.available() else blob
    except FileNotFoundError:
        key = secrets.token_bytes(32)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(dpapi.protect(key) if dpapi.available() else key)
        return key


def _mac(key: bytes, prev: str, body: str) -> str:
    return hmac.new(key, (prev + "\n" + body).encode("utf-8"), hashlib.sha256).hexdigest()


class AuditLogger:
    REDACT_KEYS = ["token", "password", "secret", "prompt", "history", "pin", "key"]

    def __init__(self, log_file: Path = AUDIT_LOG_FILE, key_file: Path = AUDIT_KEY_FILE):
        self.log_file, self.key_file = Path(log_file), Path(key_file)
        self._lock = threading.Lock()
        self._key = None
        self._last = None
        # Create file if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()

    def _sanitize(self, data: dict) -> dict:
        """Redact sensitive fields before logging. Tool arguments are logged by name only (with type
        and length): the audit log is not encrypted, and arguments can hold personal data such as
        search terms or file paths."""
        sanitized = {}
        for k, v in data.items():
            kl = str(k).lower()
            if any(rk in kl for rk in self.REDACT_KEYS):
                sanitized[k] = "[REDACTED]"
            elif kl == "args" and isinstance(v, dict):
                sanitized[k] = {ak: ("[REDACTED]" if any(rk in str(ak).lower() for rk in self.REDACT_KEYS)
                                     else f"<{type(av).__name__}, {len(str(av))} chars>") for ak, av in v.items()}
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize(v)
            elif kl in ("error", "reason", "message"):
                sanitized[k] = _PATH.sub("<path>", str(v))[:200]
            else:
                sanitized[k] = v
        return sanitized

    # ── chain state ───────────────────────────────────────────────
    def _ensure_chain(self):
        if self._key is None:
            self._key = _load_key(self.key_file)
        if self._last is None:
            self._set_aside_unchained_log()
            self._last = self._last_mac_on_disk()

    def _set_aside_unchained_log(self):
        """A log written before chaining existed is kept, renamed, and not mixed into the chain."""
        try:
            with open(self.log_file, encoding="utf-8") as f:
                first = f.readline()
        except OSError:
            return
        try:
            chained = bool(first.strip()) and "mac" in json.loads(first)
        except ValueError:
            chained = False
        if first.strip() and not chained:
            os.replace(self.log_file, self.log_file.with_name(f"{self.log_file.stem}.unchained-{int(time.time())}{self.log_file.suffix}"))
            self.log_file.touch()

    def _last_mac_on_disk(self) -> str:
        for path in [self.log_file] + [self._rotated(i) for i in range(1, KEEP_ROTATED + 1)]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    mac = json.loads(line).get("mac")
                    if mac:
                        return mac
                except ValueError:
                    continue
        return GENESIS

    def _rotated(self, i: int) -> Path:
        return self.log_file.with_name(f"{self.log_file.stem}.{i}{self.log_file.suffix}")

    def _rotate_if_needed(self):
        try:
            if self.log_file.stat().st_size < MAX_BYTES:
                return
        except OSError:
            return
        oldest = self._rotated(KEEP_ROTATED)
        if oldest.exists():
            oldest.unlink()
        for i in range(KEEP_ROTATED - 1, 0, -1):
            if self._rotated(i).exists():
                os.replace(self._rotated(i), self._rotated(i + 1))
        os.replace(self.log_file, self._rotated(1))
        self.log_file.touch()

    def log_event(self, event_type: str, details: dict):
        """Logs an event to the audit log."""
        try:
            from app.core.redaction import redact
            entry = {
                "timestamp": time.time(),
                "event_type": event_type,
                "details": self._sanitize(details)
            }
            record = json.loads(redact(json.dumps(entry, sort_keys=True)))
            body = json.dumps(record, sort_keys=True)   # exactly what verify_log() recomputes
            with self._lock:
                self._ensure_chain()
                self._rotate_if_needed()
                mac = _mac(self._key, self._last, body)
                record["prev"], record["mac"] = self._last, mac
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, sort_keys=True) + "\n")
                self._last = mac
        except Exception as e:
            # Audit log failure must be noted, but we can't crash the server.
            print(f"CRITICAL: Failed to write to audit log: {type(e).__name__}")

    def verify_log(self) -> dict:
        """Checks the chain across the rotated files (oldest first). Returns
        {"ok": bool, "entries": n, "problem": str|None}."""
        with self._lock:
            self._ensure_chain()
            key = self._key
        files = [self._rotated(i) for i in range(KEEP_ROTATED, 0, -1)] + [self.log_file]
        prev, count, first = None, 0, True
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for n, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    mac, record_prev = record.pop("mac"), record.pop("prev")
                except (ValueError, KeyError):
                    return {"ok": False, "entries": count, "problem": f"{path.name} line {n}: unreadable or unchained entry"}
                if not first and record_prev != prev:
                    return {"ok": False, "entries": count, "problem": f"{path.name} line {n}: an entry before it was removed or reordered"}
                if not hmac.compare_digest(_mac(key, record_prev, json.dumps(record, sort_keys=True)), mac):
                    return {"ok": False, "entries": count, "problem": f"{path.name} line {n}: entry was modified"}
                prev, first, count = mac, False, count + 1
        if count and prev != self._last:
            return {"ok": False, "entries": count, "problem": "the newest entries were removed"}
        return {"ok": True, "entries": count, "problem": None}


audit_logger = AuditLogger()
