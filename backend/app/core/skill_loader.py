"""
Phase 10 — Skill Loader
Registers all built-in skills via their manifests.
Called at application startup.

IMPORTANT: Existing inline tool registrations in secure_runner.py and tools.py
are preserved as the canonical source of truth for Phase 9.1 tools.
The skill system runs in parallel, registering skill-based tools alongside them.
Once all migrated tools are verified, the old inline registrations can be removed.
"""
from app.core.skill_manifest import (
    SkillManifest, SkillToolSchema, SkillCapability, GpuPolicy
)
from app.core.skill_router import skill_router
from app.core.tool_registry import RiskTier


def register_all_skills():
    """Registers all built-in skills. Called during app startup."""
    
    # ── Core Diagnostics ────────────────────────────────────
    skill_router.register_skill(SkillManifest(
        name="core_diagnostics",
        version="1.0.0",
        description="Safe read-only tools for system health and status monitoring.",
        risk_tier=RiskTier.TIER_1,
        required_capabilities=[],
        tools=[
            SkillToolSchema(
                name="skill_service_health",
                description="Returns the basic health status of the Sentinel backend.",
                parameters={}
            ),
            SkillToolSchema(
                name="skill_governor_status",
                description="Returns the current CPU/RAM Resource Governor state.",
                parameters={}
            ),
            SkillToolSchema(
                name="skill_model_state",
                description="Returns the current local AI model state.",
                parameters={}
            ),
            SkillToolSchema(
                name="skill_diagnostics",
                description="Returns safe local resource metrics (CPU and RAM usage).",
                parameters={}
            ),
        ],
        entry_point="skills.core_diagnostics",
        lazy_load=False,  # Core diagnostics should always be available
        gpu_policy=GpuPolicy.FORBIDDEN,
    ))
    
    # Map skill tool names to actual function names in the module
    _register_function_aliases("core_diagnostics", {
        "skill_service_health": "get_service_health",
        "skill_governor_status": "get_governor_status",
        "skill_model_state": "get_model_state",
        "skill_diagnostics": "get_app_diagnostics",
    })

    # ── System Ops ──────────────────────────────────────────
    skill_router.register_skill(SkillManifest(
        name="system_ops",
        version="1.0.0",
        description="Structured system operations with strict operation allowlisting.",
        risk_tier=RiskTier.TIER_3,
        required_capabilities=[SkillCapability.PROCESS_EXEC],
        tools=[
            SkillToolSchema(
                name="skill_system_op",
                description="Executes a validated system operation. Operations: get_processes, get_services, get_ip_configuration, ping_host, list_directory, echo_text.",
                parameters={
                    "operation": {
                        "type": "string",
                        "pattern": r"^(get_processes|get_services|get_ip_configuration|ping_host|list_directory|echo_text)$"
                    },
                    "target": {
                        "type": "string"
                    }
                }
            ),
        ],
        entry_point="skills.system_ops",
        lazy_load=True,
        gpu_policy=GpuPolicy.FORBIDDEN,
        requires_confirmation=True,
    ))
    
    _register_function_aliases("system_ops", {
        "skill_system_op": "run_system_op",
    })

    # ── Web Research ────────────────────────────────────────
    skill_router.register_skill(SkillManifest(
        name="web_research",
        version="1.0.0",
        description="Live internet search with SSRF protection and untrusted content wrapping.",
        risk_tier=RiskTier.TIER_2,
        required_capabilities=[SkillCapability.NETWORK_ACCESS],
        tools=[
            SkillToolSchema(
                name="skill_search_web",
                description="Searches the live internet and returns factual summaries. Results are untrusted.",
                parameters={"query": {"type": "string"}},
                required_capabilities=["network_access"]
            ),
        ],
        entry_point="skills.web_research",
        lazy_load=True,
        gpu_policy=GpuPolicy.FORBIDDEN,
        confidence_threshold=0.5,  # Require at least 50% confidence to auto-execute
    ))
    
    _register_function_aliases("web_research", {
        "skill_search_web": "search_web",
    })

    print(f"[SkillLoader] Registered {len(skill_router.get_all_manifests())} skills.")


def _register_function_aliases(skill_name: str, alias_map: dict):
    """When skill tool names differ from function names in the module,
    this patches the skill record so the router can find the right function."""
    record = skill_router._skills.get(skill_name)
    if record and record.module:
        # Module is already loaded, nothing extra needed — the resolver
        # will look up functions by tool_name, so we need to alias them.
        for tool_name, func_name in alias_map.items():
            func = getattr(record.module, func_name, None)
            if func and not hasattr(record.module, tool_name):
                setattr(record.module, tool_name, func)
    elif record:
        # Module not yet loaded — store aliases for post-load patching
        if not hasattr(record, '_aliases'):
            record._aliases = {}
        record._aliases.update(alias_map)
