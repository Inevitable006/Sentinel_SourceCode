"""
Masks secrets in anything the backend prints or logs.

Covered: per-boot session tokens (64 hex characters), raw database keys (x'...'), recovery keys
(8 groups of 4), "token=/password=/secret=/api_key=" pairs, and every value stored in the secrets
vault (registered here when saved or loaded). Installed at startup on stdout/stderr and on the
Python loggers uvicorn uses, so a stray print or error message can't leak them into log files.
"""
import logging
import re
import sys
import threading
from typing import Iterable

_PATTERNS = [
    (re.compile(r"x'[0-9a-fA-F]{32,}'"), "x'<redacted>'"),
    (re.compile(r"\b[0-9a-fA-F]{64}\b"), "<redacted>"),
    (re.compile(r"\b[A-Z2-7]{4}(?:-[A-Z2-7]{4}){7}\b"), "<redacted-recovery-key>"),
    (re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=([^&\s\"']+)"), r"\1=<redacted>"),
]
_values: set = set()
_lock = threading.Lock()
_installed = False


def register(value: str) -> None:
    """Mask this exact value from now on (secrets shorter than 6 characters are too ambiguous)."""
    if isinstance(value, str) and len(value) >= 6:
        with _lock:
            _values.add(value)


def register_many(values: Iterable[str]) -> None:
    for v in values:
        register(v)


def unregister(value: str) -> None:
    with _lock:
        _values.discard(value)


def clear_registered(_reason: str = "") -> None:
    """At lock: drop the plaintext secret values kept for masking (they are re-registered from
    the encrypted vault at the next unlock). Pattern-based masking keeps working."""
    with _lock:
        _values.clear()


def redact(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    with _lock:
        values = sorted(_values, key=len, reverse=True)
    for v in values:
        if v in text:
            text = text.replace(v, "<redacted-secret>")
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingStream:
    """Wraps stdout/stderr: every write is redacted first."""

    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        return self._inner.write(redact(s) if isinstance(s, str) else s)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class RedactingFilter(logging.Filter):
    """Redacts plain messages. Records with formatting arguments are left alone, because some
    formatters (uvicorn's access log) need those arguments; their final text is redacted by the
    RedactingStream that install() puts under every stream handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if not record.args and isinstance(record.msg, str):
                record.msg = redact(record.msg)
        except Exception:
            pass
        return True


def _wrap_handler_streams(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler.stream, RedactingStream):
            try:
                handler.setStream(RedactingStream(handler.stream))
            except Exception:
                pass


def install() -> None:
    """Called once at startup (not at import, so test output capture is left alone)."""
    global _installed
    if _installed:
        return
    _installed = True
    if not isinstance(sys.stdout, RedactingStream):
        sys.stdout = RedactingStream(sys.stdout)
    if not isinstance(sys.stderr, RedactingStream):
        sys.stderr = RedactingStream(sys.stderr)
    flt = RedactingFilter()
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.addFilter(flt)
        _wrap_handler_streams(logger)   # handlers created before startup still hold the raw streams
