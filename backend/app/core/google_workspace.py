"""Explicit, owner-initiated Google reads. OAuth and tokens never cross into chat."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from app.core import redaction, secrets_store
from app.core.egress import tool_context, egress_guard
from app.core.network_utils import SafeAsyncClient
from app.core.vault import vault

CLIENT = "google.desktop-client"
TOKENS = "google.oauth-tokens"
SCOPES = {
    "gmail": "https://www.googleapis.com/auth/gmail.readonly",
    "calendar": "https://www.googleapis.com/auth/calendar.events.readonly",
}
_mutex = threading.RLock()
_generation = 0
_pending = None


class GoogleError(ValueError):
    pass


def _ensure(generation=None):
    if not vault.is_unlocked() or (generation is not None and generation != _generation):
        raise GoogleError("Connection operation cancelled. Unlock Sentinel and try again.")


def cancel(_reason=""):
    global _generation, _pending
    with _mutex:
        _generation += 1
        if _pending:
            _pending["stop"].set()
        _pending = None


vault.add_lock_listener(cancel)


def _load(name):
    _ensure()
    value = secrets_store.get_secret(name)
    result = json.loads(value) if value else {}
    for key in ("access_token", "refresh_token", "client_secret"):
        if result.get(key):
            redaction.register(result[key])
    return result


def configure(client_id, client_secret=""):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,250}\.apps\.googleusercontent\.com", client_id):
        raise GoogleError("Import a Google Desktop app OAuth client ID.")
    if not isinstance(client_secret, str) or len(client_secret) > 1000:
        raise GoogleError("Invalid desktop client secret.")
    cancel()
    _ensure()
    secrets_store.delete_secret(TOKENS)
    secrets_store.set_secret(CLIENT, json.dumps({"client_id": client_id, "client_secret": client_secret}))
    if client_secret:
        redaction.register(client_secret)


def status():
    tokens = _load(TOKENS)
    with _mutex:
        pending = _pending
        active = bool(pending and time.monotonic() < pending["expires"])
        return {"configured": bool(_load(CLIENT)), "connected": bool(tokens.get("refresh_token") or tokens.get("access_token")),
                "gmail": SCOPES["gmail"] in tokens.get("scope", "").split(),
                "calendar": SCOPES["calendar"] in tokens.get("scope", "").split(),
                "pending": active, "callback_received": bool(active and pending.get("code")),
                "authorization_denied": bool(active and pending.get("denied"))}


def disconnect():
    cancel()
    _ensure()
    secrets_store.delete_secret(TOKENS)
    secrets_store.delete_secret(CLIENT)
    return {"disconnected": True, "note": "Local credentials removed. Remove Sentinel access in your Google Account to revoke the provider grant."}


def _accept_callback(path, pending):
    global _pending
    with _mutex:
        if _pending is not pending or time.monotonic() >= pending["expires"] or not vault.is_unlocked():
            return 410, "This sign-in has expired. Start again in Sentinel."
        if len(path) > 8192:
            return 400, "Invalid callback."
        parsed = urlsplit(path)
        values = parse_qs(parsed.query)
        state = values.get("state", [])
        if parsed.path != "/callback" or len(state) != 1 or not secrets.compare_digest(state[0].encode(), pending["state"].encode()):
            return 400, "Invalid sign-in state."
        if pending.get("code") or pending.get("denied"):
            return 409, "This sign-in response was already received."
        code = values.get("code", [])
        if values.get("error"):
            pending["denied"] = True
        elif len(code) == 1 and 1 <= len(code[0]) <= 4096:
            pending["code"] = code[0]
            redaction.register(code[0])
        else:
            return 400, "No authorization code received."
        pending["stop"].set()
        return 200, "Return to Sentinel and choose Finish connection. You can close this tab."


def start():
    global _pending
    client = _load(CLIENT)
    if not client:
        raise GoogleError("Import desktop OAuth credentials first.")
    if egress_guard.offline:
        raise GoogleError("Turn off Offline mode before connecting Google.")
    cancel()
    verifier = secrets.token_urlsafe(48)
    pending = {"state": secrets.token_urlsafe(32), "verifier": verifier,
               "expires": time.monotonic() + 300, "stop": threading.Event(), "generation": _generation}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # callback URLs contain an authorization code

        def do_GET(self):
            code, message = _accept_callback(self.path, pending)
            body = message.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Listener(HTTPServer):
        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(2)
            return sock, address

    server = Listener(("127.0.0.1", 0), Handler)
    server.timeout = .5
    pending["redirect_uri"] = f"http://127.0.0.1:{server.server_port}/callback"
    with _mutex:
        try:
            _ensure(pending["generation"])
        except GoogleError:
            server.server_close()
            raise
        _pending = pending

    def listen():
        try:
            while not pending["stop"].is_set() and time.monotonic() < pending["expires"]:
                server.handle_request()
        finally:
            server.server_close()
    threading.Thread(target=listen, daemon=True).start()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client["client_id"], "redirect_uri": pending["redirect_uri"], "response_type": "code",
        "scope": " ".join(SCOPES.values()), "state": pending["state"], "code_challenge": challenge,
        "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
    }), "expires_in": 300}


async def _request(method, url, generation, **kwargs):
    _ensure(generation)
    if urlsplit(url).netloc not in {"oauth2.googleapis.com", "gmail.googleapis.com", "www.googleapis.com"} or not url.startswith("https://"):
        raise GoogleError("Unexpected Google endpoint.")
    try:
        with tool_context("google_workspace", network_allowed=True):
            async with SafeAsyncClient(timeout=20) as client:
                response = await client.safe_request(method, url, max_redirects=0, max_bytes=2_000_000, **kwargs)
        _ensure(generation)
        if response.status_code != 200:
            raise GoogleError(f"Google returned HTTP {response.status_code}. Check consent, API setup and connection, then retry.")
        result = response.json()
        if not isinstance(result, dict):
            raise GoogleError("Google returned an unexpected response.")
        return result
    except GoogleError:
        raise
    except Exception:
        raise GoogleError("Google request failed. Check Offline mode, network access and account setup.") from None


def _save_tokens(data, generation, previous=None):
    previous = previous or {}
    if not isinstance(data.get("access_token"), str) or not data["access_token"] or data.get("token_type", "").lower() != "bearer":
        raise GoogleError("Google did not return a usable access token.")
    try:
        lifetime = min(86400, max(0, int(data.get("expires_in", 0))))
    except (TypeError, ValueError):
        raise GoogleError("Invalid Google token lifetime.") from None
    tokens = {"access_token": data["access_token"], "refresh_token": data.get("refresh_token", previous.get("refresh_token", "")),
              "scope": data.get("scope", previous.get("scope", "")), "expires_at": time.time() + lifetime}
    with _mutex:
        _ensure(generation)
        secrets_store.set_secret(TOKENS, json.dumps(tokens))
        redaction.register(tokens["access_token"])
        if tokens["refresh_token"]:
            redaction.register(tokens["refresh_token"])
    return tokens


async def finish():
    global _pending
    with _mutex:
        pending = _pending
        if not pending or time.monotonic() >= pending["expires"] or pending.get("denied") or not pending.get("code"):
            raise GoogleError("Complete browser consent first, or start again if it expired or was denied.")
        _ensure(pending["generation"])
        _pending = None  # authorization codes are single-use, including on provider failure
    client = _load(CLIENT)
    response = await _request("POST", "https://oauth2.googleapis.com/token", pending["generation"], data={
        **client, "code": pending["code"], "code_verifier": pending["verifier"],
        "redirect_uri": pending["redirect_uri"], "grant_type": "authorization_code",
    })
    _save_tokens(response, pending["generation"])
    return status()


async def _access(scope, generation):
    tokens = _load(TOKENS)
    if scope not in tokens.get("scope", "").split():
        raise GoogleError("This Google permission was not granted. Reconnect and select the requested permission.")
    if tokens.get("expires_at", 0) <= time.time() + 60:
        if not tokens.get("refresh_token"):
            raise GoogleError("Google connection expired. Reconnect in Settings.")
        response = await _request("POST", "https://oauth2.googleapis.com/token", generation, data={
            **_load(CLIENT), "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token",
        })
        tokens = _save_tokens(response, generation, tokens)
        if scope not in tokens.get("scope", "").split():
            raise GoogleError("Google permission is no longer available. Reconnect in Settings.")
    return {"Authorization": "Bearer " + tokens["access_token"]}


async def messages():
    generation = _generation
    headers = await _access(SCOPES["gmail"], generation)
    base = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    page = await _request("GET", base, generation, headers=headers, params={"maxResults": 10, "labelIds": "INBOX"})
    result = []
    for item in page.get("messages", [])[:10]:
        message_id = item.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", message_id):
            continue
        message = await _request("GET", base + "/" + message_id, generation, headers=headers,
                                 params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]})
        fields = {h.get("name", "").lower(): h.get("value", "") for h in message.get("payload", {}).get("headers", [])}
        result.append({"id": message_id, "subject": fields.get("subject", "")[:500], "from": fields.get("from", "")[:500],
                       "date": fields.get("date", "")[:100], "snippet": message.get("snippet", "")[:1000]})
    _ensure(generation)
    return {"messages": result, "more_available": bool(page.get("nextPageToken"))}


async def events():
    generation = _generation
    headers = await _access(SCOPES["calendar"], generation)
    now = datetime.now(timezone.utc)
    page = await _request("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events", generation,
                          headers=headers, params={"timeMin": now.isoformat(), "timeMax": (now + timedelta(days=7)).isoformat(),
                                                   "maxResults": 25, "singleEvents": "true", "orderBy": "startTime"})
    return {"events": [{"summary": event.get("summary", "(Untitled)")[:500],
                        "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "")),
                        "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))}
                       for event in page.get("items", [])[:25]], "more_available": bool(page.get("nextPageToken"))}
