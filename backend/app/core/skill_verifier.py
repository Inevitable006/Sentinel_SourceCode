"""
Phase 10 — Skill Verifier
Validates skill manifests and verifies module integrity before loading.
"""
import hashlib
import importlib
import os
from typing import Dict, Optional, Tuple
from app.core.skill_manifest import SkillManifest, SkillCapability


class SkillVerificationError(Exception):
    """Raised when a skill fails verification."""
    pass


class SkillVerifier:
    def __init__(self, dev_mode: bool = False):
        self._registered_tool_names: Dict[str, str] = {}  # tool_name -> skill_name
        self.dev_mode = dev_mode

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
        
        # 5. Verify module hash (integrity check)
        if manifest.module_hash and not self.dev_mode:
            actual_hash = self._compute_module_hash(manifest.entry_point)
            if actual_hash and actual_hash != manifest.module_hash:
                return False, (
                    f"Module integrity check failed for '{manifest.entry_point}'. "
                    f"Expected hash: {manifest.module_hash[:16]}..., "
                    f"Actual hash: {actual_hash[:16]}..."
                )
        
        return True, "OK"

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
                    return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            pass
        return None


skill_verifier = SkillVerifier(dev_mode=True)  # dev_mode=True during development
