"""
Egress guard: the one gate every outbound internet request passes through.

Decision order for each request (and for each redirect hop):
  1. offline mode is on                                        -> BLOCK
  2. host is on the allowlist                                  -> ALLOW
  3. the request comes from a tool that declared network_access
     (the tool already passed the policy engine and, for Tier 2+,
     your confirmation)                                        -> ALLOW
  4. anything else                                             -> BLOCK ("unexpected outbound connection")

The check runs BEFORE the DNS lookup, so a blocked host is never even resolved.

Every decision is appended to logs/egress.jsonl: time, tool, method, host, decision,
reason, HTTP status, bytes received and duration. The path, query string, headers
and body are never logged (they can contain what you searched for).

The policy (offline flag, extra allowed hosts) lives in network_policy.json, outside
the encrypted database, so it is enforced even while Sentinel is locked. If that file
exists but can't be read, Sentinel fails closed and stays offline.
"""
import collections
import contextvars
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.paths import LOGS_DIR, SENTINEL_DATA_DIR

DEFAULT_ALLOWLIST = frozenset({
    "html.duckduckgo.com",        # web search (search_web)
    "query1.finance.yahoo.com",   # market data (finance_analysis skill)
    "query2.finance.yahoo.com",
})
LOG_MAX_BYTES = 1_000_000         # rotate egress.jsonl -> egress.jsonl.1 above this size
RECENT_MAX = 200

_current_tool: contextvars.ContextVar = contextvars.ContextVar("sentinel_egress_tool", default=None)


class EgressBlocked(PermissionError):
    """Raised when the egress guard refuses an outbound request."""


@contextmanager
def tool_context(tool_name: str, network_allowed: bool):
    """Marks code running on behalf of a tool. Set by SecureRunner around every tool execution."""
    token = _current_tool.set({"tool": tool_name, "network": bool(network_allowed)})
    try:
        yield
    finally:
        _current_tool.reset(token)


def current_tool() -> Optional[Dict[str, Any]]:
    return _current_tool.get()


def _normalize_host(host: Optional[str]) -> str:
    return (host or "").strip().strip("[]").rstrip(".").lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EgressGuard:
    def __init__(self, log_path: Optional[Path] = None, policy_path: Optional[Path] = None):
        self._lock = threading.RLock()
        self._log_path = Path(log_path) if log_path else LOGS_DIR / "egress.jsonl"
        self._policy_path = Path(policy_path) if policy_path else SENTINEL_DATA_DIR / "network_policy.json"
        self._recent: collections.deque = collections.deque(maxlen=RECENT_MAX)
        self._totals = {"allowed": 0, "blocked": 0}
        self.offline = False
        self.extra_allowed: set = set()
        self._load_policy()

    # ── policy ──────────────────────────────────────────────────
    def _load_policy(self) -> None:
        try:
            data = json.loads(self._policy_path.read_text(encoding="utf-8"))
            self.offline = bool(data.get("offline", False))
            self.extra_allowed = {
                _normalize_host(h) for h in data.get("allowed_hosts", []) if isinstance(h, str) and h.strip()
            }
        except FileNotFoundError:
            pass
        except Exception as e:
            self.offline = True   # fail closed: an unreadable policy must not silently mean "online"
            print(f"[Egress] network_policy.json unreadable ({type(e).__name__}); staying OFFLINE until it is fixed")

    def _save_policy(self) -> None:
        self._policy_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._policy_path.with_name(self._policy_path.name + ".tmp")
        tmp.write_text(json.dumps({"offline": self.offline, "allowed_hosts": sorted(self.extra_allowed)}, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self._policy_path)

    def set_offline(self, enabled: bool) -> None:
        with self._lock:
            self.offline = bool(enabled)
            self._save_policy()
        self._write_log({"ts": _now_iso(), "event": "offline_mode", "enabled": bool(enabled)})

    def allowlist(self) -> List[str]:
        return sorted(DEFAULT_ALLOWLIST | self.extra_allowed)

    # ── decisions ───────────────────────────────────────────────
    def check(self, method: str, host: Optional[str]) -> Dict[str, Any]:
        """Decide one request. Returns a record to pass to record_result(), or raises EgressBlocked."""
        host = _normalize_host(host)
        ctx = _current_tool.get()
        tool = ctx["tool"] if ctx else None
        if self.offline:
            decision, reason = "blocked", "offline mode is on"
        elif host and (host in DEFAULT_ALLOWLIST or host in self.extra_allowed):
            decision, reason = "allowed", "allowlisted host"
        elif host and ctx and ctx["network"]:
            decision, reason = "allowed", f"approved tool '{tool}' has network_access"
        else:
            decision, reason = "blocked", "unexpected outbound connection (not allowlisted, not from a network tool)"
        rec = {"ts": _now_iso(), "tool": tool, "method": (method or "").upper(), "host": host,
               "decision": decision, "reason": reason, "_t0": time.monotonic()}
        if decision == "blocked":
            self._finish(rec)
            raise EgressBlocked(f"Blocked outbound request to {host or '(no host)'}: {reason}.")
        return rec

    def record_result(self, rec: Dict[str, Any], status: Optional[int] = None, bytes_in: Optional[int] = None,
                      error: Optional[str] = None, blocked_reason: Optional[str] = None) -> None:
        """Completes a record returned by check()."""
        if blocked_reason:
            rec["decision"], rec["reason"] = "blocked", blocked_reason
        if status is not None:
            rec["status"] = status
        if bytes_in is not None:
            rec["bytes_in"] = bytes_in
        if error:
            rec["error"] = error
        self._finish(rec)

    def _finish(self, rec: Dict[str, Any]) -> None:
        t0 = rec.pop("_t0", None)
        if t0 is not None:
            rec["ms"] = round((time.monotonic() - t0) * 1000)
        with self._lock:
            self._totals[rec["decision"]] += 1
            self._recent.append(dict(rec))
        self._write_log(rec)

    # ── log + status ────────────────────────────────────────────
    def _write_log(self, rec: Dict[str, Any]) -> None:
        try:
            with self._lock:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if self._log_path.stat().st_size > LOG_MAX_BYTES:
                        os.replace(self._log_path, self._log_path.with_name(self._log_path.name + ".1"))
                except FileNotFoundError:
                    pass
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Egress] could not write the egress log ({type(e).__name__})")

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Newest first."""
        with self._lock:
            items = list(self._recent)[-max(0, limit):] if limit else []
        return [dict(i) for i in reversed(items)]

    def status(self) -> Dict[str, Any]:
        with self._lock:
            last = dict(self._recent[-1]) if self._recent else None
            return {
                "offline": self.offline,
                "allowed_total": self._totals["allowed"],
                "blocked_total": self._totals["blocked"],
                "last": last,
                "allowlist": self.allowlist(),
            }


egress_guard = EgressGuard()
