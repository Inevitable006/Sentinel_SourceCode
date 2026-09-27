"""
Owner unlock: who may open Sentinel's data, and the keys that protect it.

Key layout (keystore.json in %APPDATA%\\sentinel):

  data key (32 random bytes) -- opens the encrypted database (SQLCipher raw key)
   |-- PIN wrap:      AES-256-GCM with a key derived from your PIN (Argon2id, 64 MiB, 3 passes),
   |                  then sealed with Windows DPAPI: useless without your PIN AND your Windows login
   '-- recovery wrap: AES-256-GCM with a key derived from the recovery key (160 random bits, shown
                      to you once). Not tied to Windows, so it still works after a reinstall.

keystore.json holds only wrapped keys, salts, settings and the failed-attempt counter.
Nothing in it opens your data without your PIN or recovery key.

States: setup_required --setup--> unlocked <--lock/unlock--> locked
"""
import base64
import json
import os
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core import dpapi
from app.core.paths import SENTINEL_DATA_DIR

KEYSTORE_VERSION = 1
MIN_PIN_LENGTH = 6
MAX_PIN_LENGTH = 128
KDF_PARAMS = {"iterations": 3, "lanes": 4, "memory_cost": 65536}   # ~0.3-0.5 s on a desktop CPU
FREE_ATTEMPTS = 5            # wrong PINs before waiting starts
BASE_DELAY_S = 30            # then 30 s, 60 s, 120 s ... up to MAX_DELAY_S
MAX_DELAY_S = 3600
DEFAULT_AUTO_LOCK_MIN = 15
FRESH_PIN_S = 300            # a PIN typed within 5 minutes counts as "fresh" for high-risk approvals
PIN_REQUIRED_TIER = 3        # risk tier from which an approval needs a fresh PIN (decision D6)
DPAPI_ENTROPY = b"sentinel-dek-v1"
AAD_PIN = b"sentinel-dek-v1|pin"
AAD_RECOVERY = b"sentinel-dek-v1|recovery"


class VaultError(Exception):
    """Unlock problem. The message is safe to show to the owner."""


class WrongSecret(VaultError):
    pass


class WeakPin(VaultError):
    pass


class InvalidState(VaultError):
    pass


class RateLimited(VaultError):
    def __init__(self, retry_after: int):
        super().__init__(f"Too many wrong attempts. Try again in {retry_after} seconds.")
        self.retry_after = retry_after


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pin_bytes(pin: str, *, for_new_pin: bool) -> bytes:
    if not isinstance(pin, str):
        raise WeakPin("The PIN must be text.")
    p = unicodedata.normalize("NFC", pin)
    if len(p) > MAX_PIN_LENGTH:
        raise WeakPin(f"Use at most {MAX_PIN_LENGTH} characters.")
    if for_new_pin:
        if len(p) < MIN_PIN_LENGTH:
            raise WeakPin(f"Use at least {MIN_PIN_LENGTH} characters. Longer is stronger.")
        if len(set(p)) == 1:
            raise WeakPin("Don't use the same character repeated.")
    return p.encode("utf-8")


def _pin_kek(pin_b: bytes, salt: bytes, params: Dict) -> bytes:
    return Argon2id(salt=salt, length=32, iterations=int(params["iterations"]), lanes=int(params["lanes"]),
                    memory_cost=int(params["memory_cost"])).derive(pin_b)


def _recovery_kek(rk: bytes, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"sentinel-recovery-v1").derive(rk)


def format_recovery_key(raw: bytes) -> str:
    s = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(s[i:i + 4] for i in range(0, len(s), 4))


def parse_recovery_key(text: str) -> bytes:
    s = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    try:
        raw = base64.b32decode(s + "=" * (-len(s) % 8))
    except Exception:
        raise WrongSecret("That recovery key isn't valid.")
    if len(raw) != 20:
        raise WrongSecret("That recovery key isn't valid.")
    return raw


class Vault:
    def __init__(self, keystore_path: Optional[Path] = None,
                 db_opener: Optional[Callable[[bytes, bool], Dict]] = None,
                 db_closer: Optional[Callable[[], None]] = None,
                 clock: Callable[[], float] = time.time):
        self._path = Path(keystore_path) if keystore_path else SENTINEL_DATA_DIR / "keystore.json"
        self._open_db = db_opener
        self._close_db = db_closer
        self._clock = clock
        self._lock = threading.RLock()
        self._dek: Optional[bytearray] = None
        self._last_activity = 0.0
        self._last_pin_at = 0.0
        self._auto_lock_min = DEFAULT_AUTO_LOCK_MIN
        self._listeners: List[Callable[[str], None]] = []

    # ── keystore file ───────────────────────────────────────────
    def _read(self) -> Dict:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: Dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    # ── state ───────────────────────────────────────────────────
    def state(self) -> str:
        if self._dek is not None:
            return "unlocked"
        return "locked" if self._path.exists() else "setup_required"

    def is_unlocked(self) -> bool:
        return self._dek is not None

    def status(self) -> Dict:
        with self._lock:
            ks = self._read() if self._path.exists() else {}
            return {
                "state": self.state(),
                "retry_after": self._retry_after(ks) if ks else 0,
                "failed_attempts": int(ks.get("failed_attempts", 0)) if ks else 0,
                "auto_lock_minutes": int(ks.get("auto_lock_minutes", DEFAULT_AUTO_LOCK_MIN)) if ks else DEFAULT_AUTO_LOCK_MIN,
                "windows_bound": bool(ks.get("pin", {}).get("dpapi")) if ks else dpapi.available(),
                "pin_fresh": self.pin_fresh(),
                "pin_required_tier": PIN_REQUIRED_TIER,
                "min_pin_length": MIN_PIN_LENGTH,
            }

    def add_lock_listener(self, fn: Callable[[str], None]) -> None:
        self._listeners.append(fn)

    # ── wrapping ────────────────────────────────────────────────
    def _pin_wrap(self, dek: bytes, pin_b: bytes) -> Dict:
        salt, nonce, params = secrets.token_bytes(16), secrets.token_bytes(12), dict(KDF_PARAMS)
        blob = nonce + AESGCM(_pin_kek(pin_b, salt, params)).encrypt(nonce, dek, AAD_PIN)
        bound = dpapi.available()
        if bound:
            blob = dpapi.protect(blob, DPAPI_ENTROPY)
        return {"kdf": "argon2id", "salt": _b64(salt), **params, "dpapi": bound, "wrapped": _b64(blob)}

    def _recovery_wrap(self, dek: bytes, rk: bytes) -> Dict:
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        blob = nonce + AESGCM(_recovery_kek(rk, salt)).encrypt(nonce, dek, AAD_RECOVERY)
        return {"kdf": "hkdf-sha256", "salt": _b64(salt), "wrapped": _b64(blob)}

    def _unwrap_pin(self, ks: Dict, pin_b: bytes) -> bytes:
        p = ks["pin"]
        blob = _unb64(p["wrapped"])
        if p.get("dpapi"):
            try:
                blob = dpapi.unprotect(blob, DPAPI_ENTROPY)
            except OSError:
                raise VaultError("This keystore was sealed by another Windows account or PC. Use your recovery key.")
        try:
            return AESGCM(_pin_kek(pin_b, _unb64(p["salt"]), p)).decrypt(blob[:12], blob[12:], AAD_PIN)
        except InvalidTag:
            raise WrongSecret("Wrong PIN.")

    def _unwrap_recovery(self, ks: Dict, rk: bytes) -> bytes:
        r = ks["recovery"]
        blob = _unb64(r["wrapped"])
        try:
            return AESGCM(_recovery_kek(rk, _unb64(r["salt"]))).decrypt(blob[:12], blob[12:], AAD_RECOVERY)
        except InvalidTag:
            raise WrongSecret("That recovery key doesn't match.")

    # ── rate limiting ───────────────────────────────────────────
    def _retry_after(self, ks: Dict) -> int:
        until = float(ks.get("locked_until", 0) or 0)
        now = self._clock()
        return int(until - now + 0.999) if until > now else 0

    def _register_failure(self, ks: Dict) -> None:
        n = int(ks.get("failed_attempts", 0)) + 1
        ks["failed_attempts"] = n
        if n >= FREE_ATTEMPTS:
            ks["locked_until"] = self._clock() + min(MAX_DELAY_S, BASE_DELAY_S * 2 ** (n - FREE_ATTEMPTS))
        self._write(ks)

    def _check_rate(self, ks: Dict) -> None:
        wait = self._retry_after(ks)
        if wait > 0:
            raise RateLimited(wait)

    # ── actions ─────────────────────────────────────────────────
    def _became_unlocked(self, dek: bytes, ks: Dict) -> None:
        self._dek = bytearray(dek)
        self._auto_lock_min = int(ks.get("auto_lock_minutes", DEFAULT_AUTO_LOCK_MIN))
        now = self._clock()
        self._last_activity = self._last_pin_at = now

    def setup(self, pin: str) -> Dict:
        """First run: choose a PIN. Returns the recovery key (shown once) and the migration report."""
        with self._lock:
            if self.state() != "setup_required":
                raise InvalidState("Sentinel is already set up.")
            pin_b = _pin_bytes(pin, for_new_pin=True)
            dek, rk = secrets.token_bytes(32), secrets.token_bytes(20)
            ks = {"version": KEYSTORE_VERSION, "created": _now_iso(), "auto_lock_minutes": DEFAULT_AUTO_LOCK_MIN,
                  "failed_attempts": 0, "locked_until": 0,
                  "pin": self._pin_wrap(dek, pin_b), "recovery": self._recovery_wrap(dek, rk)}
            # Open (and migrate) BEFORE writing the keystore: if that fails, nothing is half set up.
            report = self._open_db(dek, True) if self._open_db else {}
            try:
                self._write(ks)
            except Exception:
                if self._close_db:
                    self._close_db()
                raise
            self._became_unlocked(dek, ks)
            return {"recovery_key": format_recovery_key(rk), "migration": report}

    def unlock(self, pin: str) -> Dict:
        with self._lock:
            state = self.state()
            if state == "unlocked":
                return {"state": "unlocked"}
            if state == "setup_required":
                raise InvalidState("Set up Sentinel first.")
            ks = self._read()
            self._check_rate(ks)
            try:
                dek = self._unwrap_pin(ks, _pin_bytes(pin, for_new_pin=False))
            except WrongSecret:
                self._register_failure(ks)
                raise
            if self._open_db:
                self._open_db(dek, False)
            ks["failed_attempts"], ks["locked_until"] = 0, 0
            self._write(ks)
            self._became_unlocked(dek, ks)
            return {"state": "unlocked"}

    def recover(self, recovery_key: str, new_pin: str) -> Dict:
        """Forgot the PIN (or new Windows account): unlock with the recovery key and set a new PIN."""
        with self._lock:
            if self.state() == "setup_required":
                raise InvalidState("Set up Sentinel first.")
            ks = self._read()
            self._check_rate(ks)
            new_pin_b = _pin_bytes(new_pin, for_new_pin=True)
            try:
                dek = self._unwrap_recovery(ks, parse_recovery_key(recovery_key))
            except WrongSecret:
                self._register_failure(ks)
                raise
            if not self.is_unlocked() and self._open_db:
                self._open_db(dek, False)
            ks["pin"] = self._pin_wrap(dek, new_pin_b)
            ks["failed_attempts"], ks["locked_until"], ks["pin_changed"] = 0, 0, _now_iso()
            self._write(ks)
            self._became_unlocked(dek, ks)
            return {"state": "unlocked"}

    def change_pin(self, current_pin: str, new_pin: str) -> None:
        with self._lock:
            if not self.is_unlocked():
                raise InvalidState("Unlock Sentinel first.")
            ks = self._read()
            self._check_rate(ks)
            new_pin_b = _pin_bytes(new_pin, for_new_pin=True)
            try:
                dek = self._unwrap_pin(ks, _pin_bytes(current_pin, for_new_pin=False))
            except WrongSecret:
                self._register_failure(ks)
                raise
            ks["pin"] = self._pin_wrap(dek, new_pin_b)
            ks["failed_attempts"], ks["locked_until"], ks["pin_changed"] = 0, 0, _now_iso()
            self._write(ks)
            self._last_pin_at = self._last_activity = self._clock()

    def verify_pin(self, pin: str) -> None:
        """Re-check the PIN while unlocked (before a high-risk action). Makes the PIN 'fresh'."""
        with self._lock:
            if not self.is_unlocked():
                raise InvalidState("Unlock Sentinel first.")
            ks = self._read()
            self._check_rate(ks)
            try:
                self._unwrap_pin(ks, _pin_bytes(pin, for_new_pin=False))
            except WrongSecret:
                self._register_failure(ks)
                raise
            if ks.get("failed_attempts"):
                ks["failed_attempts"], ks["locked_until"] = 0, 0
                self._write(ks)
            self._last_pin_at = self._last_activity = self._clock()

    def lock(self, reason: str = "manual") -> None:
        with self._lock:
            if self._dek is None:
                return
            try:
                if self._close_db:
                    self._close_db()
            finally:
                for i in range(len(self._dek)):   # best effort: Python can't guarantee memory wiping
                    self._dek[i] = 0
                self._dek = None
                self._last_pin_at = 0.0
        for fn in list(self._listeners):
            try:
                fn(reason)
            except Exception as e:
                print(f"[Vault] lock listener failed: {type(e).__name__}")

    # ── activity, auto-lock, fresh PIN ──────────────────────────
    def touch(self) -> None:
        if self._dek is not None:
            self._last_activity = self._clock()

    def check_auto_lock(self) -> bool:
        if self._dek is None or not self._auto_lock_min:
            return False
        if self._clock() - self._last_activity >= self._auto_lock_min * 60:
            self.lock("idle")
            return True
        return False

    def set_auto_lock_minutes(self, minutes: int) -> int:
        minutes = int(minutes)
        if minutes < 0 or minutes > 24 * 60:
            raise VaultError("Choose between 0 (never) and 1440 minutes.")
        with self._lock:
            if not self.is_unlocked():
                raise InvalidState("Unlock Sentinel first.")
            ks = self._read()
            ks["auto_lock_minutes"] = minutes
            self._write(ks)
            self._auto_lock_min = minutes
            return minutes

    def pin_fresh(self) -> bool:
        return self._dek is not None and (self._clock() - self._last_pin_at) <= FRESH_PIN_S

    def needs_pin_for_tier(self, tier: int) -> bool:
        return tier >= PIN_REQUIRED_TIER and not self.pin_fresh()


def _make_default_vault() -> Vault:
    from app.db import database
    return Vault(db_opener=database.open_for_vault, db_closer=database.close_database)


vault = _make_default_vault()
