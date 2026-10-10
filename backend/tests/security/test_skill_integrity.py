"""F07: release policy refuses modified skills, at registration and at lazy load."""
import hashlib
import json
import sys

import pytest

from app.core.skill_manifest import SkillManifest, SkillToolSchema
from app.core.skill_verifier import SkillVerifier, SkillVerificationError, PIN_FILE
from app.core.tool_registry import RiskTier


def _skill_package(tmp_path, monkeypatch, body="def hello():\n    return 'hi'\n"):
    pkg = tmp_path / "pinned_test_skill"
    pkg.mkdir()
    init = pkg / "__init__.py"
    init.write_text(body)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("pinned_test_skill", None)
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"modules": {"pinned_test_skill": hashlib.sha256(init.read_bytes()).hexdigest()}}))
    manifest = SkillManifest(name="pinned_test", description="t", risk_tier=RiskTier.TIER_1,
                             tools=[SkillToolSchema(name="hello", description="t")], entry_point="pinned_test_skill")
    return init, pins, manifest


def test_release_policy_is_the_default():
    from app.core.skill_verifier import skill_verifier
    assert skill_verifier.dev_mode is False
    assert PIN_FILE.is_file()


def test_builtin_skills_match_their_pins():
    v = SkillVerifier(dev_mode=False)
    for entry, expected in v.pinned_hashes().items():
        assert v._compute_module_hash(entry) == expected, f"{entry} changed; re-run tools/pin_skills.py if intended"


def test_modified_module_is_refused_at_registration(tmp_path, monkeypatch):
    init, pins, manifest = _skill_package(tmp_path, monkeypatch)
    init.write_text("def hello():\n    return 'tampered'\n")
    ok, msg = SkillVerifier(dev_mode=False, pin_file=pins).verify_manifest(manifest)
    assert not ok and "integrity" in msg


def test_modification_after_registration_is_refused_at_load(tmp_path, monkeypatch):
    init, pins, manifest = _skill_package(tmp_path, monkeypatch)
    v = SkillVerifier(dev_mode=False, pin_file=pins)
    assert v.verify_manifest(manifest) == (True, "OK")
    init.write_text("def hello():\n    return 'tampered'\n")
    with pytest.raises(SkillVerificationError):
        v.load_verified_module(manifest)
    assert "pinned_test_skill" not in sys.modules


def test_verified_bytes_are_what_runs(tmp_path, monkeypatch):
    init, pins, manifest = _skill_package(tmp_path, monkeypatch)
    v = SkillVerifier(dev_mode=False, pin_file=pins)
    assert v.verify_manifest(manifest)[0]
    assert v.load_verified_module(manifest).hello() == "hi"


def test_missing_pin_file_fails_closed(tmp_path, monkeypatch):
    _, _, manifest = _skill_package(tmp_path, monkeypatch)
    ok, msg = SkillVerifier(dev_mode=False, pin_file=tmp_path / "absent.json").verify_manifest(manifest)
    assert not ok and "missing" in msg


def test_unpinned_module_is_refused(tmp_path, monkeypatch):
    _, _, manifest = _skill_package(tmp_path, monkeypatch)
    manifest.entry_point = "json"   # a real module that is not in the pin list
    ok, msg = SkillVerifier(dev_mode=False, pin_file=tmp_path / "pins.json").verify_manifest(manifest)
    assert not ok and "not in the pinned" in msg
