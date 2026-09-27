"""
Owner unlock (Phase 1, step 1.3): PIN + Windows binding + recovery key, rate limiting,
auto-lock, the fresh-PIN rule, and the fixes from the independent review (keystore backup,
clock tampering, never "locked" with the database open).
Uses a temporary keystore, fake clocks and fake database hooks.
"""
import base64
import json
import sys

import pytest

from app.core import vault as vmod
from app.core.vault import InvalidState, RateLimited, Vault, VaultError, WeakPin, WrongSecret

PIN, PIN2 = "blue-482915", "river-771133"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(vmod, "KDF_PARAMS", {"iterations": 1, "lanes": 1, "memory_cost": 8192})


class FakeDb:
    def __init__(self):
        self.opened, self.closed, self.key, self.options = [], 0, None, {}

    def open(self, key, first_setup, **options):
        self.key, self.options = bytes(key), options
        self.opened.append((self.key, first_setup))
        return {"migrated": first_setup}

    def close(self):
        self.closed += 1


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture()
def env(tmp_path):
    db, wall, mono = FakeDb(), Clock(), Clock(50.0)
    path = tmp_path / "keystore.json"
    v = Vault(keystore_path=path, db_opener=db.open, db_closer=db.close, clock=wall, monotonic=mono)
    return v, db, wall, mono, path


def _new(path, db, wall, mono, **kw):
    return Vault(keystore_path=path, db_opener=db.open, db_closer=db.close, clock=wall, monotonic=mono, **kw)


# ── setup / unlock ──────────────────────────────────────────────

def test_first_run_needs_setup(env):
    v, *_ = env
    assert v.state() == "setup_required"
    with pytest.raises(InvalidState):
        v.unlock(PIN)


def test_setup_returns_recovery_key_and_opens_the_database(env):
    v, db, *_ = env
    out = v.setup(PIN)
    assert v.state() == "unlocked"
    assert db.opened == [(db.key, True)] and len(db.key) == 32 and db.options == {"remove_test_rows": True}
    rk = out["recovery_key"]
    assert len(rk.replace("-", "")) == 32 and rk.count("-") == 7
    assert out["migration"] == {"migrated": True}


def test_setup_can_keep_old_test_rows(env):
    v, db, *_ = env
    v.setup(PIN, remove_test_rows=False)
    assert db.options == {"remove_test_rows": False}


def test_keystore_holds_no_usable_secret(env):
    v, db, _, _, path = env
    rk = v.setup(PIN)["recovery_key"]
    for f in (path, path.with_name("keystore.backup.json")):
        raw = f.read_text(encoding="utf-8")
        for secret in (PIN, rk, rk.replace("-", ""), db.key.hex(), base64.b64encode(db.key).decode()):
            assert secret not in raw
    ks = json.loads(path.read_text())
    assert ks["pin"]["kdf"] == "argon2id" and ks["recovery"]["kdf"] == "hkdf-sha256"
    if sys.platform == "win32":
        assert ks["pin"]["dpapi"] is True


def test_default_argon2_cost_is_128_mib():
    assert vmod.DEFAULT_KDF_PARAMS["memory_cost"] >= 131072 and vmod.DEFAULT_KDF_PARAMS["iterations"] >= 3


def test_lock_then_unlock_with_the_pin(env):
    v, db, *_ = env
    v.setup(PIN)
    key = db.key
    v.lock()
    assert v.state() == "locked" and db.closed == 1
    v.unlock(PIN)
    assert v.state() == "unlocked" and db.opened[-1] == (key, False)


@pytest.mark.parametrize("bad", ["12345", "12345678", "123456789", "aaaaaaaa", "abababab", "", "x" * 200])
def test_weak_pins_are_rejected(env, bad):
    v, *_ = env
    with pytest.raises(WeakPin):
        v.setup(bad)
    assert v.state() == "setup_required"


@pytest.mark.parametrize("good", ["1234567890", "blue-4829", "correct horse battery"])
def test_reasonable_pins_are_accepted(env, good):
    v, *_ = env
    v.setup(good)
    assert v.state() == "unlocked"


# ── wrong PINs and waiting ──────────────────────────────────────

def test_wrong_pin_is_refused_and_counted(env):
    v, _, _, _, path = env
    v.setup(PIN)
    v.lock()
    with pytest.raises(WrongSecret):
        v.unlock("000000")
    assert json.loads(path.read_text())["failed_attempts"] == 1
    v.unlock(PIN)
    assert json.loads(path.read_text())["failed_attempts"] == 0


def test_rate_limit_after_five_wrong_pins_survives_a_restart(env):
    v, db, wall, mono, path = env
    v.setup(PIN)
    v.lock()
    for _ in range(vmod.FREE_ATTEMPTS):
        with pytest.raises(WrongSecret):
            v.unlock("000000")
    with pytest.raises(RateLimited) as e:
        v.unlock(PIN)                                        # even the right PIN has to wait
    assert e.value.retry_after == vmod.BASE_DELAY_S
    v2 = _new(path, db, wall, mono)                          # app restarted
    with pytest.raises(RateLimited):
        v2.unlock(PIN)
    wall.t += vmod.BASE_DELAY_S + 1
    v2.unlock(PIN)
    assert v2.state() == "unlocked"


def test_waiting_time_doubles(env):
    v, _, wall, _, _ = env
    v.setup(PIN)
    v.lock()
    for _ in range(vmod.FREE_ATTEMPTS):
        with pytest.raises(WrongSecret):
            v.unlock("000000")
    wall.t += vmod.BASE_DELAY_S + 1
    with pytest.raises(WrongSecret):
        v.unlock("000000")
    with pytest.raises(RateLimited) as e:
        v.unlock("000000")
    assert e.value.retry_after == 2 * vmod.BASE_DELAY_S


def test_clock_set_back_never_means_waiting_longer_than_the_maximum(env):
    v, _, wall, _, _ = env
    v.setup(PIN)
    v.lock()
    for _ in range(vmod.FREE_ATTEMPTS):
        with pytest.raises(WrongSecret):
            v.unlock("000000")
    wall.t -= 365 * 86400                                    # someone sets the clock back a year
    with pytest.raises(RateLimited) as e:
        v.unlock(PIN)
    assert e.value.retry_after <= vmod.MAX_DELAY_S
    wall.t += vmod.MAX_DELAY_S + 1
    v.unlock(PIN)


# ── recovery ────────────────────────────────────────────────────

def test_recovery_key_unlocks_and_sets_a_new_pin(env):
    v, db, *_ = env
    rk = v.setup(PIN)["recovery_key"]
    key = db.key
    v.lock()
    v.recover(rk.lower().replace("-", " "), PIN2)             # forgiving about case and spaces
    assert v.state() == "unlocked" and db.opened[-1] == (key, False)
    v.lock()
    with pytest.raises(WrongSecret):
        v.unlock(PIN)                                        # the old PIN no longer works
    v.unlock(PIN2)


def test_wrong_or_malformed_recovery_key(env):
    v, *_ = env
    v.setup(PIN)
    v.lock()
    with pytest.raises(WrongSecret):
        v.recover("AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA", PIN2)
    with pytest.raises(WrongSecret):
        v.recover("not a key", PIN2)


def test_new_recovery_key_replaces_the_old_one(env):
    v, _, _, mono, _ = env
    old = v.setup(PIN)["recovery_key"]
    new = v.new_recovery_key()                               # PIN is fresh right after setup
    assert new != old
    v.lock()
    with pytest.raises(WrongSecret):
        v.recover(old, PIN2)
    v.recover(new, PIN2)
    mono.t += vmod.FRESH_PIN_S + 1
    with pytest.raises(VaultError):
        v.new_recovery_key()                                 # needs a fresh PIN


def test_change_pin(env):
    v, *_ = env
    v.setup(PIN)
    with pytest.raises(WrongSecret):
        v.change_pin("000000", PIN2)
    v.change_pin(PIN, PIN2)
    v.lock()
    v.unlock(PIN2)


# ── keystore robustness (review finding 1) ──────────────────────

def test_missing_keystore_is_restored_from_the_backup(env):
    v, db, wall, mono, path = env
    v.setup(PIN)
    v.lock()
    path.unlink()
    v2 = _new(path, db, wall, mono)
    assert v2.state() == "locked"
    v2.unlock(PIN)
    assert path.exists()                                     # main copy rebuilt from the backup


def test_damaged_keystore_falls_back_to_the_backup(env):
    v, db, wall, mono, path = env
    v.setup(PIN)
    v.lock()
    path.write_text("", encoding="utf-8")                    # e.g. a crash left it empty
    _new(path, db, wall, mono).unlock(PIN)


def test_both_copies_gone_but_database_present_refuses_a_new_setup(tmp_path):
    db = FakeDb()
    v = Vault(keystore_path=tmp_path / "keystore.json", db_opener=db.open, db_closer=db.close,
              db_exists=lambda: True)
    assert v.state() == "keystore_missing"
    with pytest.raises(InvalidState, match="keystore is missing"):
        v.setup(PIN)
    assert db.opened == []


def test_unlock_does_not_rewrite_the_keystore_when_nothing_changed(env, monkeypatch):
    v, *_ = env
    v.setup(PIN)
    v.lock()
    writes = []
    real = vmod._atomic_write_json
    monkeypatch.setattr(vmod, "_atomic_write_json", lambda p, d: (writes.append(p.name), real(p, d)))
    v.unlock(PIN)
    assert writes == []


def test_failed_setup_leaves_nothing_half_done(tmp_path):
    def boom(key, first_setup, **options):
        raise RuntimeError("disk full")
    v = Vault(keystore_path=tmp_path / "k.json", db_opener=boom, db_closer=lambda: None)
    with pytest.raises(RuntimeError):
        v.setup(PIN)
    assert v.state() == "setup_required" and not (tmp_path / "k.json").exists()


# ── never "locked" with the database open (review finding 2b) ───

def test_lock_always_closes_the_database(env):
    v, db, *_ = env
    v.lock()                                                 # even when it thinks it is locked
    assert db.closed == 1


def test_unlock_failing_after_open_closes_the_database(env, monkeypatch):
    v, db, *_ = env
    v.setup(PIN)
    v.lock()
    for _ in range(2):
        with pytest.raises(WrongSecret):
            v.unlock("000000")                               # leaves a counter that unlock must clear
    closed_before = db.closed

    def disk_full(ks):
        raise OSError("disk full")
    monkeypatch.setattr(v, "_clear_failures", disk_full)
    with pytest.raises(OSError):
        v.unlock(PIN)
    assert v.state() == "locked" and db.closed == closed_before + 1


# ── auto-lock and fresh PIN (monotonic clock; review finding 3) ─

def test_auto_lock_after_idle_time(env):
    v, _, _, mono, _ = env
    v.setup(PIN)
    idle = vmod.DEFAULT_AUTO_LOCK_MIN * 60
    mono.t += idle - 5
    assert v.check_auto_lock() is False
    v.touch()
    mono.t += idle - 5
    assert v.check_auto_lock() is False and v.state() == "unlocked"
    mono.t += 10
    assert v.check_auto_lock() is True and v.state() == "locked"


def test_auto_lock_setting_persists_and_zero_means_never(env):
    v, _, _, mono, path = env
    v.setup(PIN)
    v.set_auto_lock_minutes(0)
    mono.t += 10 * 3600
    assert v.check_auto_lock() is False
    assert json.loads(path.read_text())["auto_lock_minutes"] == 0
    with pytest.raises(VaultError):
        v.set_auto_lock_minutes(-1)


def test_fresh_pin_window_for_high_risk_actions(env):
    v, _, _, mono, _ = env
    v.setup(PIN)
    assert v.pin_fresh() and not v.needs_pin_for_tier(4)
    mono.t += vmod.FRESH_PIN_S + 1
    assert not v.pin_fresh()
    assert v.needs_pin_for_tier(vmod.PIN_REQUIRED_TIER)
    assert not v.needs_pin_for_tier(vmod.PIN_REQUIRED_TIER - 1)
    with pytest.raises(WrongSecret):
        v.verify_pin("000000")
    v.verify_pin(PIN)
    assert v.pin_fresh()


def test_setting_the_wall_clock_back_does_not_keep_the_pin_fresh(env):
    v, _, wall, mono, _ = env
    v.setup(PIN)
    mono.t += vmod.FRESH_PIN_S + 1
    wall.t -= 10 * 86400                                     # only the wall clock can be changed by a user
    assert not v.pin_fresh()


def test_lock_listeners_hear_the_reason(env):
    v, *_ = env
    heard = []
    v.add_lock_listener(heard.append)
    v.setup(PIN)
    v.lock("idle")
    assert heard == ["idle"]


def test_recovery_key_format_round_trip():
    raw = bytes(range(20))
    assert vmod.parse_recovery_key(vmod.format_recovery_key(raw)) == raw


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_pin_wrap_only_opens_for_this_windows_account(env, monkeypatch):
    v, *_ = env
    v.setup(PIN)
    v.lock()

    def other_account(blob, entropy=b""):
        raise OSError(13, "CryptUnprotectData failed")

    monkeypatch.setattr(vmod.dpapi, "unprotect", other_account)
    with pytest.raises(VaultError, match="another Windows account"):
        v.unlock(PIN)
