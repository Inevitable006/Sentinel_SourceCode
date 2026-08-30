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

    def _sanitize(self, data: dict) -> dict:
        """Redact sensitive fields from the data before logging."""
        sanitized = {}
        redact_keys = ["token", "password", "secret", "prompt", "history"]
        for k, v in data.items():
            if any(rk in k.lower() for rk in redact_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize(v)
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
