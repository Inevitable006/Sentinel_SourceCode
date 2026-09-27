import json
import time
from pathlib import Path
from app.core.paths import SENTINEL_DATA_DIR

AUDIT_LOG_FILE = SENTINEL_DATA_DIR / "audit.log"

class AuditLogger:
    def __init__(self):
        # Create file if it doesn't exist
        if not AUDIT_LOG_FILE.exists():
            AUDIT_LOG_FILE.touch()

    REDACT_KEYS = ["token", "password", "secret", "prompt", "history", "pin", "key"]

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
            elif kl == "error":
                sanitized[k] = str(v)[:200]
            else:
                sanitized[k] = v
        return sanitized

    def log_event(self, event_type: str, details: dict):
        """Logs an event to the audit log."""
        try:
            entry = {
                "timestamp": time.time(),
                "event_type": event_type,
                "details": self._sanitize(details)
            }
            with open(AUDIT_LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            # Audit log failure must be noted, but we can't crash the server.
            # In a real environment, we'd alert monitoring.
            print(f"CRITICAL: Failed to write to audit log: {e}")
            pass

audit_logger = AuditLogger()
