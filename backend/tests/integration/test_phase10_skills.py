"""
Phase 10 — Modular Skill System Test Suite
Tests skill manifests, router, verifier, lazy loading, capability enforcement,
GPU policy, confidence threshold, and full regression compatibility.
"""
import sys
import os
import time
import json

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.skill_manifest import (
    SkillManifest, SkillToolSchema, SkillCapability, GpuPolicy
)
from app.core.skill_router import skill_router, SkillRouter
from app.core.skill_verifier import SkillVerifier
from app.core.tool_registry import tool_registry, RiskTier
from app.core.policy_engine import policy_engine, PolicyDecision
from app.core.resource_governor import resource_governor, SystemState

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1


# ============================================================
# TEST 1: Manifest Validation
# ============================================================
def test_manifest_validation():
    print("\n[Test 1] Manifest Validation")
    
    # 1a: Valid manifest
    try:
        m = SkillManifest(
            name="test_valid",
            description="A valid test skill.",
            risk_tier=RiskTier.TIER_1,
            tools=[SkillToolSchema(name="test_tool", description="A test tool.")],
            entry_point="skills.core_diagnostics"
        )
        check("Valid manifest creates successfully", True)
    except Exception as e:
        check("Valid manifest creates successfully", False)
    
    # 1b: Missing required fields
    try:
        SkillManifest(
            name="test_invalid",
            description="",  # empty description violates min_length
            risk_tier=RiskTier.TIER_1,
            tools=[SkillToolSchema(name="t", description="d")],
            entry_point="some.module"
        )
        check("Empty description rejected", False)
    except Exception:
        check("Empty description rejected", True)
    
    # 1c: Invalid skill name pattern
    try:
        SkillManifest(
            name="Invalid-Name!",
            description="Bad name.",
            risk_tier=RiskTier.TIER_1,
            tools=[SkillToolSchema(name="t", description="d")],
            entry_point="some.module"
        )
        check("Invalid skill name pattern rejected", False)
    except Exception:
        check("Invalid skill name pattern rejected", True)
    
    # 1d: Duplicate tool names within manifest
    try:
        SkillManifest(
            name="test_dupes",
            description="Has duplicates.",
            risk_tier=RiskTier.TIER_1,
            tools=[
                SkillToolSchema(name="same_name", description="Tool 1"),
                SkillToolSchema(name="same_name", description="Tool 2"),
            ],
            entry_point="some.module"
        )
        check("Duplicate tool names within manifest rejected", False)
    except Exception:
        check("Duplicate tool names within manifest rejected", True)
    
    # 1e: No tools
    try:
        SkillManifest(
            name="test_empty",
            description="No tools.",
            risk_tier=RiskTier.TIER_1,
            tools=[],
            entry_point="some.module"
        )
        check("Empty tools list rejected", False)
    except Exception:
        check("Empty tools list rejected", True)


# ============================================================
# TEST 2: Skill Registration
# ============================================================
def test_skill_registration():
    print("\n[Test 2] Skill Registration and Tool Registry Integration")
    
    # The skill_loader already ran during import of app.core modules.
    # Check that skill-based tools are in the registry.
    from app.core.skill_loader import register_all_skills
    
    # Check skill_service_health exists
    tool = tool_registry.get_tool("skill_service_health")
    check("skill_service_health registered in tool_registry", tool is not None)
    
    if tool:
        check("skill_service_health is TIER_1", tool.tool_schema.risk_tier == RiskTier.TIER_1)
    
    # Check skill_system_op exists
    tool2 = tool_registry.get_tool("skill_system_op")
    check("skill_system_op registered in tool_registry", tool2 is not None)
    
    if tool2:
        check("skill_system_op is TIER_3", tool2.tool_schema.risk_tier == RiskTier.TIER_3)
    
    # Check skill_search_web exists
    tool3 = tool_registry.get_tool("skill_search_web")
    check("skill_search_web registered in tool_registry", tool3 is not None)
    
    if tool3:
        check("skill_search_web is TIER_2", tool3.tool_schema.risk_tier == RiskTier.TIER_2)


# ============================================================
# TEST 3: Lazy Loading
# ============================================================
def test_lazy_loading():
    print("\n[Test 3] Lazy Loading")
    
    # system_ops has lazy_load=True
    record = skill_router._skills.get("system_ops")
    check("system_ops skill record exists", record is not None)
    
    # web_research has lazy_load=True
    record_web = skill_router._skills.get("web_research")
    check("web_research skill record exists", record_web is not None)
    
    # core_diagnostics has lazy_load=False — should be pre-loaded
    record_core = skill_router._skills.get("core_diagnostics")
    check("core_diagnostics is pre-loaded (lazy_load=False)", 
          record_core is not None and record_core.is_loaded)


# ============================================================
# TEST 4: Capability Enforcement
# ============================================================
def test_capability_enforcement():
    print("\n[Test 4] Capability Enforcement")
    
    # system_ops requires PROCESS_EXEC
    manifest = skill_router.resolve_skill("skill_system_op")
    check("system_ops declares PROCESS_EXEC capability",
          manifest is not None and SkillCapability.PROCESS_EXEC in manifest.required_capabilities)
    
    # web_research requires NETWORK_ACCESS
    manifest_web = skill_router.resolve_skill("skill_search_web")
    check("web_research declares NETWORK_ACCESS capability",
          manifest_web is not None and SkillCapability.NETWORK_ACCESS in manifest_web.required_capabilities)
    
    # core_diagnostics has no dangerous capabilities
    manifest_core = skill_router.resolve_skill("skill_service_health")
    check("core_diagnostics has no dangerous capabilities",
          manifest_core is not None and len(manifest_core.required_capabilities) == 0)


# ============================================================
# TEST 5: GPU Policy
# ============================================================
def test_gpu_policy():
    print("\n[Test 5] GPU Policy")
    
    # All current skills are FORBIDDEN (no GPU needed)
    for skill_name in ["core_diagnostics", "system_ops", "web_research"]:
        manifest = skill_router._skills[skill_name].manifest
        check(f"{skill_name} has GPU policy = FORBIDDEN",
              manifest.gpu_policy == GpuPolicy.FORBIDDEN)
    
    # Test that gpu_required skill would be blocked without GPU
    verifier = SkillVerifier(dev_mode=True)
    # PROCESS_EXEC with TIER_3 and GPU_REQUIRED with gpu_policy mismatch
    try:
        m = SkillManifest(
            name="test_gpu_mismatch",
            description="GPU mismatch test.",
            risk_tier=RiskTier.TIER_3,
            required_capabilities=[SkillCapability.GPU_REQUIRED],
            tools=[SkillToolSchema(name="gpu_tool", description="Needs GPU.")],
            entry_point="skills.core_diagnostics",
            gpu_policy=GpuPolicy.FORBIDDEN  # Mismatch!
        )
        ok, msg = verifier.verify_manifest(m)
        check("GPU capability with FORBIDDEN policy rejected", not ok)
    except Exception:
        check("GPU capability with FORBIDDEN policy rejected", True)


# ============================================================
# TEST 6: Confidence Threshold
# ============================================================
def test_confidence_threshold():
    print("\n[Test 6] Confidence Threshold")
    
    # web_research has confidence_threshold=0.5
    check("High confidence passes threshold",
          skill_router.check_confidence("skill_search_web", 0.8))
    
    check("Low confidence fails threshold",
          not skill_router.check_confidence("skill_search_web", 0.3))
    
    check("Exact threshold passes",
          skill_router.check_confidence("skill_search_web", 0.5))
    
    # core_diagnostics has no threshold (default 0.0)
    check("No-threshold skill passes any confidence",
          skill_router.check_confidence("skill_service_health", 0.0))


# ============================================================
# TEST 7: Skill Verifier Integrity
# ============================================================
def test_verifier_integrity():
    print("\n[Test 7] Skill Verifier Integrity")
    
    verifier = SkillVerifier(dev_mode=False)
    
    # Test PROCESS_EXEC must be TIER_3+
    m = SkillManifest(
        name="test_low_tier_exec",
        description="Bad tier for PROCESS_EXEC.",
        risk_tier=RiskTier.TIER_1,
        required_capabilities=[SkillCapability.PROCESS_EXEC],
        tools=[SkillToolSchema(name="bad_exec", description="Should fail.")],
        entry_point="skills.core_diagnostics",
    )
    ok, msg = verifier.verify_manifest(m)
    check("PROCESS_EXEC with TIER_1 rejected", not ok)
    
    # Test duplicate tool detection
    verifier2 = SkillVerifier(dev_mode=True)
    m1 = SkillManifest(
        name="test_skill_a",
        description="First skill.",
        risk_tier=RiskTier.TIER_1,
        tools=[SkillToolSchema(name="unique_tool_xyz", description="Tool.")],
        entry_point="skills.core_diagnostics",
    )
    ok1, _ = verifier2.verify_manifest(m1)
    verifier2.register_tool_names(m1)
    
    m2 = SkillManifest(
        name="test_skill_b",
        description="Second skill with duplicate tool.",
        risk_tier=RiskTier.TIER_1,
        tools=[SkillToolSchema(name="unique_tool_xyz", description="Duplicate!")],
        entry_point="skills.core_diagnostics",
    )
    ok2, msg2 = verifier2.verify_manifest(m2)
    check("Duplicate tool name across skills rejected", not ok2)


# ============================================================
# TEST 8: Skill Unloading
# ============================================================
def test_skill_unloading():
    print("\n[Test 8] Skill Unloading")
    
    # Ensure core_diagnostics is loaded
    record = skill_router._skills.get("core_diagnostics")
    check("core_diagnostics is loaded before unload", record.is_loaded)
    
    # Unload it
    skill_router.unload_skill("core_diagnostics")
    check("core_diagnostics is unloaded after unload_skill", not record.is_loaded)
    
    # Re-load by triggering the module load manually
    skill_router._load_module("core_diagnostics")
    check("core_diagnostics re-loaded successfully", record.is_loaded)


# ============================================================
# TEST 9: Existing Tools Regression
# ============================================================
def test_existing_tools_regression():
    print("\n[Test 9] Existing Phase 9.1 tools still work")
    
    # Trigger legacy inline tool registrations
    import app.core.secure_runner  # registers get_service_health, run_system_op, etc.
    import app.core.tools          # registers search_web, get_system_telemetry
    
    # The original inline-registered tools must still be present
    check("get_service_health still registered (legacy)",
          tool_registry.get_tool("get_service_health") is not None)
    check("run_system_op still registered (legacy)",
          tool_registry.get_tool("run_system_op") is not None)
    check("search_web still registered (legacy)",
          tool_registry.get_tool("search_web") is not None)
    check("get_system_telemetry still registered (legacy)",
          tool_registry.get_tool("get_system_telemetry") is not None)
    
    # Execute a legacy tool through secure_runner
    from app.core.secure_runner import secure_runner
    result = secure_runner.execute("get_service_health", {}, "regression_test")
    check("Legacy get_service_health executes successfully",
          result["status"] == "success")


# ============================================================
# TEST 10: ResourceGovernor Integration
# ============================================================
def test_governor_integration():
    print("\n[Test 10] ResourceGovernor integration with skills")
    
    # In EMERGENCY, skill tools should be blocked at the policy level
    resource_governor.state = SystemState.EMERGENCY
    
    decision, _ = policy_engine.evaluate("skill_service_health", {}, "s1")
    check("Skill tool blocked in EMERGENCY state", decision == PolicyDecision.DENY)
    
    resource_governor.state = SystemState.IDLE
    
    decision2, _ = policy_engine.evaluate("skill_service_health", {}, "s1")
    check("Skill tool allowed in IDLE state", decision2 == PolicyDecision.ALLOW)


# ============================================================
# TEST 11: Skill Status API
# ============================================================
def test_skill_status():
    print("\n[Test 11] Skill Status API")
    
    status = skill_router.get_skill_status("core_diagnostics")
    check("Skill status returns valid data", status is not None)
    check("Status includes name", status.get("name") == "core_diagnostics")
    check("Status includes loaded flag", "loaded" in status)
    check("Status includes tools list", isinstance(status.get("tools"), list))
    check("Status includes risk_tier", "risk_tier" in status)
    
    # All manifests
    manifests = skill_router.get_all_manifests()
    check("get_all_manifests returns 5 skills", len(manifests) == 5)


# ============================================================
# TEST 12: Manifest Enumeration
# ============================================================
def test_skill_manifests():
    print("\n[Test 12] Skill Manifest Enumeration")
    
    manifests = skill_router.get_all_manifests()
    names = {m.name for m in manifests}
    check("core_diagnostics in manifests", "core_diagnostics" in names)
    check("system_ops in manifests", "system_ops" in names)
    check("web_research in manifests", "web_research" in names)
    check("python_coding in manifests", "python_coding" in names)
    check("document_analysis in manifests", "document_analysis" in names)


# ============================================================
# TEST 13: Subprocess Argument Capture & Python-Native Verification
# ============================================================
def test_subprocess_argument_capture():
    print("\n[Test 13] Subprocess Argument Capture (system_ops)")
    from app.core.safe_process import safe_process
    from skills.system_ops import run_system_op
    import unittest.mock

    # Mock safe_process.run_command to capture args instead of executing
    with unittest.mock.patch.object(safe_process, 'run_command', return_value=(True, "mocked", "")) as mock_run:
        # Test get_processes
        run_system_op("get_processes")
        cmd_args = mock_run.call_args[0][0]
        check("get_processes uses fixed command with no interpolation",
              cmd_args[-1] == "Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet | ConvertTo-Json -Depth 1")
        
        # Test get_services
        run_system_op("get_services")
        cmd_args = mock_run.call_args[0][0]
        check("get_services uses fixed command with no interpolation",
              cmd_args[-1] == "Get-Service | Where-Object Status -eq 'Running' | Select-Object Name, DisplayName | ConvertTo-Json -Depth 1")
              
        # Test get_ip_configuration
        run_system_op("get_ip_configuration")
        cmd_args = mock_run.call_args[0][0]
        check("get_ip_configuration uses fixed command with no interpolation",
              cmd_args[-1] == "Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress | ConvertTo-Json -Depth 1")

        # Test ping_host
        run_system_op("ping_host", "google.com")
        cmd_args = mock_run.call_args[0][0]
        check("ping_host passes target as discrete argument, not interpolated script",
              cmd_args == [r"c:\windows\system32\ping.exe", "-n", "4", "google.com"])
              
        # Test Python-native commands (should NOT call run_command)
        mock_run.reset_mock()
        run_system_op("echo_text", "hello")
        run_system_op("list_directory", "C:\\")
        check("echo_text and list_directory are Python-native (no subprocess)", 
              mock_run.call_count == 0)


# ============================================================
# RUN ALL
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PHASE 10 — MODULAR SKILL SYSTEM TEST SUITE")
    print("=" * 60)
    
    # Trigger skill loading
    from app.core.skill_loader import register_all_skills
    try:
        register_all_skills()
    except Exception as e:
        # Skills may already be registered if imports triggered it
        print(f"Note: {e}")
    
    test_manifest_validation()
    test_skill_registration()
    test_lazy_loading()
    test_capability_enforcement()
    test_gpu_policy()
    test_confidence_threshold()
    test_verifier_integrity()
    test_skill_unloading()
    test_existing_tools_regression()
    test_governor_integration()
    test_skill_status()
    test_skill_manifests()
    test_subprocess_argument_capture()
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)
    
    if failed > 0:
        print("\n*** PHASE 10 EXIT GATE: FAIL ***")
        exit(1)
    else:
        print("\n*** PHASE 10 EXIT GATE: PASS ***")
