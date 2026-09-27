"""
Owner unlock (Phase 1, step 1.3): PIN + Windows binding + recovery key, rate limiting,
auto-lock and the fresh-PIN rule for high-risk approvals.
Uses a temporary keystore, a fake clock and fake database hooks.
"""
import base64
import json
import sys

import pytest

from app.core import vault as vmod
from app.core.vault import InvalidState, RateLimited, Vault, VaultError, WeakPin, WrongSecret


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(vmod, "KDF_PARAMS", {"iterations": 1, "lanes": 1, "memory_cost": 8192})


class FakeDb:
    def __init__(self):
        self.opened, self.closed, self.key = [], 0, None

    def open(self, key, first_setup):
        self.key = bytes(key)
        self.opened.append((self.key, first_setup))
        return {"migrated": first_setup}

    def close(self):
        self.closed += 1


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture()
def env(tmp_path):
    db, clock = FakeDb(), Clock()
    path = tmp_path / "keystore.json"
    return Vault(keystore_path=path, db_opener=db.open, db_closer=db.close, clock=clock), db, clock, path


def test_first_run_needs_setup(env):
    v, *_ = env
    assert v.state() == "setup_required"
    with pytest.raises(InvalidState):
        v.unlock("482915")


def test_setup_returns_recovery_key_and_opens_the_database(env):
    v, db, _, _ = env
    out = v.setup("482915")
    assert v.state() == "unlocked"
    assert db.opened == [(db.key, True)] and len(db.key) == 32
    rk = out["recovery_key"]
    assert len(rk.replace("-", "")) == 32 and rk.count("-") == 7
    assert out["migration"] == {"migrated": True}


def test_keystore_holds_no_usable_secret(env):
    v, db, _, path = env
    rk = v.setup("482915")["recovery_key"]
    raw = path.read_text(encoding="utf-8")
    for secret in ("482915", rk, rk.replace("-", ""), db.key.hex(), base64.b64encode(db.key).decode()):
        assert secret not in raw
    ks = json.loads(raw)
    assert ks["pin"]["kdf"] == "argon2id" and ks["recovery"]["kdf"] == "hkdf-sha256"
    if sys.platform == "win32":
        assert ks["pin"]["dpapi"] is True


def test_lock_then_unlock_with_the_pin(env):
    v, db, _, _ = env
    v.setup("482915")
    key = db.key
    v.lock()
    assert v.state() == "locked" and db.closed == 1
    v.unlock("482915")
    assert v.state() == "unlocked" and db.opened[-1] == (key, False)


def test_wrong_pin_is_refused_and_counted(env):
    v, _, _, path = env
    v.setup("482915")
    v.lock()
    with pytest.raises(WrongSecret):
        v.unlock("000000")
    assert json.loads(path.read_text())["failed_attempts"] == 1
    v.unlock("482915")
    assert json.loads(path.read_text())["failed_attempts"] == 0


def test_rate_limit_after_five_wrong_pins_survives_a_restart(env):
    v, db, clock, path = env
    v.setup("482915")
    v.lock()
    for _ in range(vmod.FREE_ATTEMPTS):
        with pytest.raises(WrongSecret):
            v.unlock("000000")
    with pytest.raises(RateLimited) as e:
        v.unlock("482915")                                   # even the right PIN has to wait
    assert e.value.retry_after == vmod.BASE_DELAY_S
    v2 = Vault(keystore_path=path, db_opener=db.open, db_closer=db.close, clock=clock)   # app restarted
    with pytest.raises(RateLimited):
        v2.unlock("482915")
    clock.t += vmod.BASE_DELAY_S + 1
    v2.unlock("482915")
    assert v2.state() == "unlocked"


def test_waiting_time_doubles(env):
    v, _, clock, _ = env
    v.setup("482915")
    v.lock()
    for _ in range(vmod.FREE_ATTEMPTS):
        with pytest.raises(WrongSecret):
            v.unlock("000000")
    clock.t += vmod.BASE_DELAY_S + 1
    with pytest.raises(WrongSecret):
        v.unlock("000000")
    with pytest.raises(RateLimited) as e:
        v.unlock("000000")
    assert e.value.retry_after == 2 * vmod.BASE_DELAY_S


@pytest.mark.parametrize("bad", ["12345", "aaaaaa", "", "x" * 200])
def test_weak_pins_are_rejected(env, bad):
    v, *_ = env
    with pytest.raises(WeakPin):
        v.setup(bad)
    assert v.state() == "setup_required"


def test_recovery_key_unlocks_and_sets_a_new_pin(env):
    v, db, _, _ = env
    rk = v.setup("482915")["recovery_key"]
    key = db.key
    v.lock()
    v.recover(rk.lower().replace("-", " "), "771133")        # forgiving about case and spaces
    assert v.state() == "unlocked" and db.opened[-1] == (key, False)
    v.lock()
    with pytest.raises(WrongSecret):
        v.unlock("482915")                                   # the old PIN no longer works
    v.unlock("771133")


def test_wrong_or_malformed_recovery_key(env):
    v, *_ = env
    v.setup("482915")
    v.lock()
    with pytest.raises(WrongSecret):
        v.recover("AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA", "771133")
    with pytest.raises(WrongSecret):
        v.recover("not a key", "771133")


def test_change_pin(env):
    v, *_ = env
    v.setup("482915")
    with pytest.raises(WrongSecret):
        v.change_pin("000000", "771133")
    v.change_pin("482915", "771133")
    v.lock()
    v.unlock("771133")


def test_failed_setup_leaves_nothing_half_done(tmp_path):
    def boom(key, first_setup):
        raise RuntimeError("disk full")
    v = Vault(keystore_path=tmp_path / "k.json", db_opener=boom, db_closer=lambda: None)
    with pytest.raises(RuntimeError):
        v.setup("482915")
    assert v.state() == "setup_required" and not (tmp_path / "k.json").exists()


def test_auto_lock_after_idle_time(env):
    v, _, clock, _ = env
    v.setup("482915")
    idle = vmod.DEFAULT_AUTO_LOCK_MIN * 60
    clock.t += idle - 5
    assert v.check_auto_lock() is False
    v.touch()
    clock.t += idle - 5
    assert v.check_auto_lock() is False and v.state() == "unlocked"
    clock.t += 10
    assert v.check_auto_lock() is True and v.state() == "locked"


def test_auto_lock_setting_persists_and_zero_means_never(env):
    v, _, clock, path = env
    v.setup("482915")
    v.set_auto_lock_minutes(0)
    clock.t += 10 * 3600
    assert v.check_auto_lock() is False
    assert json.loads(path.read_text())["auto_lock_minutes"] == 0
    with pytest.raises(VaultError):
        v.set_auto_lock_minutes(-1)


def test_fresh_pin_window_for_high_risk_actions(env):
    v, _, clock, _ = env
    v.setup("482915")
    assert v.pin_fresh() and not v.needs_pin_for_tier(4)
    clock.t += vmod.FRESH_PIN_S + 1
    assert not v.pin_fresh()
    assert v.needs_pin_for_tier(vmod.PIN_REQUIRED_TIER)
    assert not v.needs_pin_for_tier(vmod.PIN_REQUIRED_TIER - 1)
    with pytest.raises(WrongSecret):
        v.verify_pin("000000")
    v.verify_pin("482915")
    assert v.pin_fresh()


def test_lock_listeners_hear_the_reason(env):
    v, *_ = env
    heard = []
    v.add_lock_listener(heard.append)
    v.setup("482915")
    v.lock("idle")
    assert heard == ["idle"]


def test_recovery_key_format_round_trip():
    raw = bytes(range(20))
    assert vmod.parse_recovery_key(vmod.format_recovery_key(raw)) == raw


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_pin_wrap_only_opens_for_this_windows_account(env, monkeypatch):
    v, *_ = env
    v.setup("482915")
    v.lock()

    def other_account(blob, entropy=b""):
        raise OSError(13, "CryptUnprotectData failed")

    monkeypatch.setattr(vmod.dpapi, "unprotect", other_account)
    with pytest.raises(VaultError, match="another Windows account"):
        v.unlock("482915")
