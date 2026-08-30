import hashlib
import hmac
import secrets
import time
import json
from typing import Optional

# Ephemeral token store for this session
_TOKEN_STORE = {}

class TokenService:
    def __init__(self):
        # A server-side cryptographic secret that changes every restart
        self._server_secret = secrets.token_bytes(32)

    def _hash_action(self, tool_name: str, args: dict) -> str:
        """Creates a canonical digest of the action arguments."""
        canonical_args = json.dumps(args, sort_keys=True)
        message = f"{tool_name}:{canonical_args}".encode("utf-8")
        return hmac.new(self._server_secret, message, hashlib.sha256).hexdigest()

    def generate_token(self, session_id: str, tool_name: str, args: dict, risk_tier: int, expiry_seconds: int = 120) -> str:
        """Generates a single-use token bound to the specific action and session.
        TIER_4 tokens are unconditionally rejected as defense-in-depth."""
        if risk_tier >= 4:
            raise ValueError("TIER_4 actions are permanently blocked. Token generation refused.")
        
        action_digest = self._hash_action(tool_name, args)
        token_val = secrets.token_urlsafe(32)
        
        _TOKEN_STORE[token_val] = {
            "session_id": session_id,
            "tool_name": tool_name,
            "action_digest": action_digest,
            "risk_tier": risk_tier,
            "expires_at": time.time() + expiry_seconds,
            "used": False
        }
        return token_val

    def validate_token(self, token_val: str, session_id: str, tool_name: str, args: dict) -> bool:
        """Validates that a token is unused, unexpired, and matches the requested action."""
        record = _TOKEN_STORE.get(token_val)
        if not record:
            return False
            
        if record["used"]:
            return False
            
        if time.time() > record["expires_at"]:
            return False
            
        if record["session_id"] != session_id:
            return False
            
        if record["tool_name"] != tool_name:
            return False
            
        current_digest = self._hash_action(tool_name, args)
        if record["action_digest"] != current_digest:
            return False
            
        # Mark as used (single-use)
        record["used"] = True
        return True

    def cleanup_expired(self):
        """Removes expired and used tokens to prevent unbounded memory growth."""
        now = time.time()
        expired_keys = [k for k, v in _TOKEN_STORE.items() if v["used"] or now > v["expires_at"]]
        for k in expired_keys:
            del _TOKEN_STORE[k]
        return len(expired_keys)

token_service = TokenService()
