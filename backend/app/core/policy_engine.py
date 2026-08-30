from enum import Enum
from typing import Dict, Any, Tuple
from app.core.tool_registry import tool_registry, RiskTier
from app.core.resource_governor import resource_governor, SystemState
from app.core.audit_logger import audit_logger

class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_CONFIRMATION = "needs_confirmation"

class PolicyEngine:
    def __init__(self):
        self.version = "1.0.0"

    def evaluate(self, tool_name: str, args: dict, session_id: str) -> Tuple[PolicyDecision, str]:
        """Evaluates a tool request against the policy engine."""
        
        # 1. Look up tool
        tool_def = tool_registry.get_tool(tool_name)
        if not tool_def:
            reason = "Unknown tool requested."
            self._audit(tool_name, None, args, PolicyDecision.DENY, reason, session_id)
            return PolicyDecision.DENY, reason
            
        risk_tier = tool_def.tool_schema.risk_tier

        # 2. Check Governor State
        if resource_governor.state in [SystemState.EMERGENCY, SystemState.USER_PAUSED]:
            reason = f"System is currently in {resource_governor.state.value} state. Nonessential tools blocked."
            self._audit(tool_name, risk_tier, args, PolicyDecision.DENY, reason, session_id)
            return PolicyDecision.DENY, reason

        # 3. Validate Schema
        # Check no unexpected arguments
        expected_args = set(tool_def.tool_schema.parameters.keys())
        provided_args = set(args.keys())
        if not provided_args.issubset(expected_args):
            extra = provided_args - expected_args
            reason = f"Invalid schema: unpermitted arguments {extra}."
            self._audit(tool_name, risk_tier, args, PolicyDecision.DENY, reason, session_id)
            return PolicyDecision.DENY, reason

        # Validate argument types and patterns
        import re
        TYPE_MAP = {"string": str, "int": int, "integer": int, "float": float, "bool": bool, "boolean": bool}
        for param_name, param_spec in tool_def.tool_schema.parameters.items():
            if param_name in args:
                val = args[param_name]
                expected_type_str = param_spec.get("type", "string")
                expected_type = TYPE_MAP.get(expected_type_str)
                if expected_type and not isinstance(val, expected_type):
                    reason = f"Invalid type for argument '{param_name}': expected {expected_type_str}, got {type(val).__name__}."
                    self._audit(tool_name, risk_tier, args, PolicyDecision.DENY, reason, session_id)
                    return PolicyDecision.DENY, reason
                
                # Enforce regex pattern if specified
                pattern = param_spec.get("pattern")
                if pattern and isinstance(val, str):
                    if not re.match(pattern, val):
                        reason = f"Security violation: Argument '{param_name}' does not match allowed pattern '{pattern}'."
                        self._audit(tool_name, risk_tier, args, PolicyDecision.DENY, reason, session_id)
                        return PolicyDecision.DENY, reason

        # 4. Decide based on Risk Tier
        if risk_tier in [RiskTier.TIER_0, RiskTier.TIER_1]:
            decision = PolicyDecision.ALLOW
            reason = "Allowed by default for low-risk read-only tools."
        elif risk_tier == RiskTier.TIER_2:
            decision = PolicyDecision.NEEDS_CONFIRMATION
            reason = "Read access requires confirmation."
        elif risk_tier == RiskTier.TIER_3:
            decision = PolicyDecision.NEEDS_CONFIRMATION
            reason = "Modification requires confirmation."
        else: # TIER_4 or unknown
            decision = PolicyDecision.DENY
            reason = "High-risk tool execution is disabled by policy."

        self._audit(tool_name, risk_tier, args, decision, reason, session_id)
        return decision, reason

    def _audit(self, tool_name: str, risk_tier: RiskTier, args: dict, decision: PolicyDecision, reason: str, session_id: str):
        audit_logger.log_event("policy_evaluation", {
            "session_id": session_id,
            "tool_name": tool_name,
            "risk_tier": risk_tier.value if risk_tier else None,
            "decision": decision.value,
            "reason": reason,
            "policy_version": self.version,
            "args": args
        })

policy_engine = PolicyEngine()
