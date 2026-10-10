"""
Phase 10 — Skill Verifier
Validates skill manifests and verifies module integrity before registration and again at load.

Release policy (the default): every skill module must match the SHA-256 pinned in
backend/skill-hashes.json, both when it is registered and when it is lazily loaded, and the
module is executed from exactly the bytes that were checked (never from a .pyc cache).
A missing or unreadable pin file refuses every skill (fails closed).
Development policy (SENTINEL_SKILL_DEV=1): hashes are not enforced, so skills can be edited.
After editing a skill, re-pin with: backend\\.venv\\Scripts\\python tools\\pin_skills.py
This is integrity checking with a locally pinned list, not code signing.
"""
import hashlib
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from app.core.skill_manifest import SkillManifest, SkillCapability

PIN_FILE = Path(__file__).resolve().parents[2] / "skill-hashes.json"


class SkillVerificationError(Exception):
    """Raised when a skill fails verification."""
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SkillVerifier:
    def __init__(self, dev_mode: bool = False, pin_file: Path = PIN_FILE):
        self._registered_tool_names: Dict[str, str] = {}  # tool_name -> skill_name
        self.dev_mode = dev_mode
        self.pin_file = pin_file

    def pinned_hashes(self) -> Optional[Dict[str, str]]:
        try:
            data = json.loads(Path(self.pin_file).read_text(encoding="utf-8"))
            pins = data["modules"]
            if not isinstance(pins, dict):
                return None
            return {str(k): str(v) for k, v in pins.items()}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def verify_manifest(self, manifest: SkillManifest) -> Tuple[bool, str]:
        """Validates a skill manifest before registration.
        Returns (success, error_message)."""

        # 1. Check for duplicate tool names across skills
        for tool in manifest.tools:
            if tool.name in self._registered_tool_names:
                owner = self._registered_tool_names[tool.name]
                return False, (
                    f"Tool '{tool.name}' is already registered by skill '{owner}'. "
                    f"Duplicate tool names across skills are forbidden."
                )

        # 2. Verify entry_point module can be found
        try:
            spec = importlib.util.find_spec(manifest.entry_point)
            if spec is None or spec.origin is None:
                return False, f"Entry point module '{manifest.entry_point}' not found."
        except (ModuleNotFoundError, ValueError) as e:
            return False, f"Entry point module '{manifest.entry_point}' cannot be located: {e}"

        # 3. Capability audit: GPU_REQUIRED should match gpu_policy
        if SkillCapability.GPU_REQUIRED in manifest.required_capabilities:
            if manifest.gpu_policy not in ("required", "preferred"):
                return False, (
                    "Skill declares GPU_REQUIRED capability but gpu_policy is "
                    f"'{manifest.gpu_policy}'. Use 'required' or 'preferred'."
                )

        # 4. PROCESS_EXEC must be TIER_3 or higher
        if SkillCapability.PROCESS_EXEC in manifest.required_capabilities:
            if manifest.risk_tier.value < 3:
                return False, (
                    "Skill with PROCESS_EXEC capability must be TIER_3 or higher."
                )

        # 5. Integrity: the module must match its pinned hash (release policy)
        if not self.dev_mode:
            pins = self.pinned_hashes()
            if pins is None:
                return False, "Skill hash list (skill-hashes.json) is missing or unreadable; skills are disabled."
            expected = pins.get(manifest.entry_point)
            if not expected:
                return False, f"Module '{manifest.entry_point}' is not in the pinned skill list."
            if manifest.module_hash and manifest.module_hash != expected:
                return False, f"Manifest hash for '{manifest.entry_point}' does not match the pinned hash."
            actual_hash = self._compute_module_hash(manifest.entry_point)
            if actual_hash != expected:
                return False, (
                    f"Module integrity check failed for '{manifest.entry_point}'. "
                    f"Expected hash: {expected[:16]}..., "
                    f"Actual hash: {(actual_hash or 'unreadable')[:16]}..."
                )
            manifest.module_hash = expected
        elif manifest.module_hash:
            actual_hash = self._compute_module_hash(manifest.entry_point)
            if actual_hash and actual_hash != manifest.module_hash:
                return False, f"Module integrity check failed for '{manifest.entry_point}'."

        return True, "OK"

    def load_verified_module(self, manifest: SkillManifest):
        """Imports a skill module. In release policy the source is read once, its hash is
        checked against the pin, and those exact bytes are executed."""
        if self.dev_mode:
            return importlib.import_module(manifest.entry_point)
        existing = sys.modules.get(manifest.entry_point)
        spec = importlib.util.find_spec(manifest.entry_point)
        if spec is None or not spec.origin or not os.path.isfile(spec.origin):
            raise SkillVerificationError(f"Module '{manifest.entry_point}' not found.")
        with open(spec.origin, "rb") as f:
            source = f.read()
        pins = self.pinned_hashes() or {}
        expected = pins.get(manifest.entry_point)
        if not expected or _sha256(source) != expected or (manifest.module_hash and manifest.module_hash != expected):
            raise SkillVerificationError(
                f"Module '{manifest.entry_point}' changed since it was verified; refusing to load it.")
        if existing is not None and getattr(existing, "__sentinel_verified_hash__", None) == expected:
            return existing
        # If something imported the module earlier (possibly from a .pyc), re-run the verified
        # source inside that same module object, so every reference ends up on checked code.
        module = existing if existing is not None else importlib.util.module_from_spec(spec)
        sys.modules[manifest.entry_point] = module
        try:
            exec(compile(source, spec.origin, "exec"), module.__dict__)
        except BaseException:
            if existing is None:
                sys.modules.pop(manifest.entry_point, None)
            raise
        module.__sentinel_verified_hash__ = expected
        return module

    def register_tool_names(self, manifest: SkillManifest):
        """Records tool names as owned by this skill (for duplicate detection)."""
        for tool in manifest.tools:
            self._registered_tool_names[tool.name] = manifest.name

    def unregister_tool_names(self, manifest: SkillManifest):
        """Removes tool name ownership when a skill is unloaded."""
        for tool in manifest.tools:
            self._registered_tool_names.pop(tool.name, None)

    def compute_and_set_hash(self, manifest: SkillManifest) -> Optional[str]:
        """Computes the SHA-256 hash of the skill module and sets it on the manifest."""
        h = self._compute_module_hash(manifest.entry_point)
        if h:
            manifest.module_hash = h
        return h

    def _compute_module_hash(self, entry_point: str) -> Optional[str]:
        """Computes SHA-256 hash of the entry_point module file."""
        try:
            spec = importlib.util.find_spec(entry_point)
            if spec and spec.origin and os.path.isfile(spec.origin):
                with open(spec.origin, "rb") as f:
                    return _sha256(f.read())
        except Exception:
            pass
        return None


# Release policy unless development mode is explicitly requested.
skill_verifier = SkillVerifier(dev_mode=os.environ.get("SENTINEL_SKILL_DEV") == "1")
