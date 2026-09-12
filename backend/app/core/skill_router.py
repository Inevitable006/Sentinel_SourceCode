"""
Phase 10 — Skill Router
Central hub for skill lifecycle: registration, resolution, lazy loading,
capability enforcement, GPU policy, and memory integration.

All tools from skills are registered into the existing tool_registry,
so the PolicyEngine, SecureRunner, and TokenService work unchanged.
"""
import importlib
import time
from typing import Dict, List, Optional, Any, Callable
from app.core.skill_manifest import (
    SkillManifest, SkillCapability, GpuPolicy, SkillToolSchema
)
from app.core.skill_verifier import skill_verifier
from app.core.tool_registry import tool_registry, ToolDefinition, ToolSchema, RiskTier
from app.core.audit_logger import audit_logger


class SkillLoadError(Exception):
    pass


class SkillRecord:
    """Internal record tracking a registered skill's state."""
    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self.module = None           # Lazy: loaded on first call
        self.loaded_at: Optional[float] = None
        self.last_used: Optional[float] = None
        self.call_count: int = 0

    @property
    def is_loaded(self) -> bool:
        return self.module is not None


class SkillRouter:
    def __init__(self):
        self._skills: Dict[str, SkillRecord] = {}       # skill_name -> SkillRecord
        self._tool_to_skill: Dict[str, str] = {}         # tool_name -> skill_name

    # ── Registration ────────────────────────────────────────────

    def register_skill(self, manifest: SkillManifest) -> bool:
        """Validates and registers a skill. Tools are added to tool_registry."""
        # 1. Verify manifest
        ok, msg = skill_verifier.verify_manifest(manifest)
        if not ok:
            audit_logger.log_event("skill_registration_failed", {
                "skill": manifest.name, "reason": msg
            })
            raise ValueError(f"Skill '{manifest.name}' registration failed: {msg}")

        # 2. Check for duplicate skill name
        if manifest.name in self._skills:
            raise ValueError(f"Skill '{manifest.name}' is already registered.")

        # 3. Register tool names with verifier (for cross-skill duplicate detection)
        skill_verifier.register_tool_names(manifest)

        # 4. Compute module hash if not set
        if not manifest.module_hash:
            skill_verifier.compute_and_set_hash(manifest)

        # 5. Create the SkillRecord
        record = SkillRecord(manifest)
        self._skills[manifest.name] = record

        # 6. Register each tool in the global tool_registry
        for tool_schema in manifest.tools:
            self._register_skill_tool(manifest, tool_schema)
            self._tool_to_skill[tool_schema.name] = manifest.name

        # 7. If not lazy, load immediately
        if not manifest.lazy_load:
            self._load_module(manifest.name)

        audit_logger.log_event("skill_registered", {
            "skill": manifest.name,
            "version": manifest.version,
            "tools": [t.name for t in manifest.tools],
            "risk_tier": manifest.risk_tier.value,
            "lazy": manifest.lazy_load
        })
        return True

    def _register_skill_tool(self, manifest: SkillManifest, tool_schema: SkillToolSchema):
        """Creates a ToolDefinition with a wrapper executor that enforces
        capability checks, GPU policy, lazy loading, and output caps."""

        def make_executor(skill_name: str, tool_name: str):
            def skill_tool_executor(**kwargs):
                return self._execute_skill_tool(skill_name, tool_name, kwargs)
            return skill_tool_executor

        # Determine confirmation requirement
        # If manifest overrides, use that. Otherwise, defer to tier-based policy.
        capabilities = [c for c in tool_schema.required_capabilities]
        if not capabilities:
            capabilities = [c.value for c in manifest.required_capabilities]

        td = ToolDefinition(
            tool_schema=ToolSchema(
                name=tool_schema.name,
                description=tool_schema.description,
                risk_tier=manifest.risk_tier,
                parameters=tool_schema.parameters,
                required_capabilities=capabilities
            ),
            executor=make_executor(manifest.name, tool_schema.name)
        )
        tool_registry.register(td)

    # ── Execution ───────────────────────────────────────────────

    def _execute_skill_tool(self, skill_name: str, tool_name: str, args: dict) -> Any:
        """Internal executor called by tool_registry -> secure_runner -> here."""
        record = self._skills.get(skill_name)
        if not record:
            return f"Error: Skill '{skill_name}' not found."

        manifest = record.manifest

        # GPU policy check
        gpu_ok, gpu_msg = self._check_gpu_policy(manifest)
        if not gpu_ok:
            return gpu_msg

        # ResourceGovernor check for GPU-heavy skills
        if SkillCapability.GPU_REQUIRED in manifest.required_capabilities:
            from app.core.resource_governor import resource_governor, SystemState
            if resource_governor.state in [SystemState.HIGH_LOAD, SystemState.EMERGENCY]:
                return (
                    f"Error: Skill '{skill_name}' requires GPU but system is in "
                    f"{resource_governor.state.value} state."
                )

        # Lazy load the module
        if not record.is_loaded:
            self._load_module(skill_name)

        # Find and call the tool function
        func = self._resolve_tool_function(record, tool_name)
        if func is None:
            return f"Error: Tool function '{tool_name}' not found in skill module '{skill_name}'."

        # Inject memory access if the skill has the capability
        enriched_args = self._inject_capabilities(manifest, args)

        # Execute with output cap
        try:
            result = func(**enriched_args)
            result_str = str(result)
            max_bytes = manifest.max_output_bytes
            if len(result_str) > max_bytes:
                result_str = result_str[:max_bytes] + "\n... [TRUNCATED by skill output cap]"
            record.last_used = time.time()
            record.call_count += 1
            return result_str
        except Exception as e:
            return f"Error: Skill '{skill_name}' tool '{tool_name}' failed: {e}"

    def _resolve_tool_function(self, record: SkillRecord, tool_name: str) -> Optional[Callable]:
        """Resolves the tool function from the loaded module."""
        module = record.module
        if module is None:
            return None
        # Look for a function matching the tool name
        func = getattr(module, tool_name, None)
        if callable(func):
            return func
        return None

    # ── Capability Injection ────────────────────────────────────

    def _inject_capabilities(self, manifest: SkillManifest, args: dict) -> dict:
        """Injects capability-gated services into the args if the skill declares them."""
        enriched = args.copy()

        if SkillCapability.MEMORY_READ in manifest.required_capabilities:
            from app.core.memory_service import memory_service
            enriched["_memory_read"] = memory_service.retrieve_relevant_memory

        if SkillCapability.MEMORY_WRITE in manifest.required_capabilities:
            from app.core.memory_service import memory_service
            enriched["_memory_write"] = memory_service.remember

        return enriched

    # ── GPU Policy ──────────────────────────────────────────────

    def _check_gpu_policy(self, manifest: SkillManifest):
        """Checks GPU availability against the skill's GPU policy."""
        if manifest.gpu_policy == GpuPolicy.REQUIRED:
            if not self._is_gpu_available():
                return False, (
                    f"Error: Skill '{manifest.name}' requires GPU but no GPU is available."
                )
            # Check VRAM pressure
            vram = self._get_vram_percent()
            if vram is not None and vram > 85.0:
                return False, (
                    f"Error: Skill '{manifest.name}' requires GPU but VRAM is at {vram:.0f}% "
                    f"(threshold: 85%). Deferring to protect system stability."
                )
        return True, "OK"

    def _is_gpu_available(self) -> bool:
        """Checks if an NVIDIA GPU is available."""
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=2
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception:
            return False

    def _get_vram_percent(self) -> Optional[float]:
        """Gets current VRAM usage percentage."""
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                used, total = float(parts[0]), float(parts[1])
                return (used / total) * 100 if total > 0 else None
        except Exception:
            pass
        return None

    # ── Module Loading ──────────────────────────────────────────

    def _load_module(self, skill_name: str):
        """Lazy-loads the skill's Python module."""
        record = self._skills.get(skill_name)
        if not record:
            raise SkillLoadError(f"Skill '{skill_name}' not found.")
        if record.is_loaded:
            return

        manifest = record.manifest
        try:
            module = importlib.import_module(manifest.entry_point)
            record.module = module
            record.loaded_at = time.time()
            
            # Apply function aliases if set by skill_loader
            if hasattr(record, '_aliases'):
                for tool_name, func_name in record._aliases.items():
                    func = getattr(module, func_name, None)
                    if func and not hasattr(module, tool_name):
                        setattr(module, tool_name, func)
            
            audit_logger.log_event("skill_module_loaded", {
                "skill": skill_name,
                "entry_point": manifest.entry_point
            })
        except Exception as e:
            raise SkillLoadError(
                f"Failed to load module '{manifest.entry_point}' for skill '{skill_name}': {e}"
            )

    # ── Resolution & Lifecycle ──────────────────────────────────

    def resolve_skill(self, tool_name: str) -> Optional[SkillManifest]:
        """Looks up which skill owns a given tool name."""
        skill_name = self._tool_to_skill.get(tool_name)
        if skill_name and skill_name in self._skills:
            return self._skills[skill_name].manifest
        return None

    def unload_skill(self, skill_name: str):
        """Unloads a skill module to free memory. The skill remains registered."""
        record = self._skills.get(skill_name)
        if record and record.is_loaded:
            record.module = None
            record.loaded_at = None
            import gc
            gc.collect()
            audit_logger.log_event("skill_module_unloaded", {"skill": skill_name})

    def unregister_skill(self, skill_name: str):
        """Completely removes a skill and its tools."""
        record = self._skills.get(skill_name)
        if not record:
            return
        # Remove tools from registry
        for tool_schema in record.manifest.tools:
            if tool_schema.name in tool_registry.tools:
                del tool_registry.tools[tool_schema.name]
            self._tool_to_skill.pop(tool_schema.name, None)
        # Remove from verifier
        skill_verifier.unregister_tool_names(record.manifest)
        # Remove from router
        del self._skills[skill_name]
        audit_logger.log_event("skill_unregistered", {"skill": skill_name})

    def get_all_manifests(self) -> List[SkillManifest]:
        """Returns all registered skill manifests."""
        return [r.manifest for r in self._skills.values()]

    def get_skill_status(self, skill_name: str) -> Optional[dict]:
        """Returns status info about a skill."""
        record = self._skills.get(skill_name)
        if not record:
            return None
        return {
            "name": record.manifest.name,
            "version": record.manifest.version,
            "loaded": record.is_loaded,
            "loaded_at": record.loaded_at,
            "last_used": record.last_used,
            "call_count": record.call_count,
            "tools": [t.name for t in record.manifest.tools],
            "risk_tier": record.manifest.risk_tier.value,
            "gpu_policy": record.manifest.gpu_policy.value,
        }

    def check_confidence(self, tool_name: str, confidence: any) -> bool:
        """Returns True if confidence meets the skill's threshold.
        If confidence is below threshold or unknown, the caller should escalate
        to NEEDS_CONFIRMATION regardless of tier."""
        manifest = self.resolve_skill(tool_name)
        if manifest and manifest.confidence_threshold > 0:
            if confidence == "unknown":
                return False
            try:
                conf_val = float(confidence)
                return conf_val >= manifest.confidence_threshold
            except (ValueError, TypeError):
                return False
        return True  # No threshold set, confidence is sufficient


skill_router = SkillRouter()
