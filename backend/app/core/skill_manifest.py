"""
Phase 10 — Skill Manifest Schema
Defines the canonical manifest format for all Sentinel skills.
Each skill must declare its capabilities, risk tier, tools, GPU policy,
and other metadata required by the Security Gate.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from app.core.tool_registry import RiskTier


class SkillCapability(str, Enum):
    """Declared capabilities that a skill may request.
    The Skill Router enforces these at load and execution time."""
    NETWORK_ACCESS = "network_access"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    PROCESS_EXEC = "process_exec"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    GPU_REQUIRED = "gpu_required"


class SkillToolSchema(BaseModel):
    """Schema for a single tool exposed by a skill."""
    name: str
    description: str
    parameters: Dict[str, Any] = {}
    required_capabilities: List[str] = []


class GpuPolicy(str, Enum):
    """How a skill relates to GPU resources."""
    REQUIRED = "required"       # Skill cannot function without GPU
    PREFERRED = "preferred"     # Falls back to CPU transparently
    OPTIONAL = "optional"       # No GPU preference
    FORBIDDEN = "forbidden"     # Must run CPU-only


class SkillManifest(BaseModel):
    """Complete manifest for a Sentinel skill module."""
    name: str = Field(..., min_length=1, max_length=64,
                      pattern=r"^[a-z][a-z0-9_]*$")
    version: str = "1.0.0"
    description: str = Field(..., min_length=1, max_length=512)
    author: str = "sentinel-core"

    risk_tier: RiskTier
    required_capabilities: List[SkillCapability] = []
    tools: List[SkillToolSchema] = Field(..., min_length=1)

    entry_point: str = Field(..., min_length=1)     # Python module path
    lazy_load: bool = True
    max_output_bytes: int = Field(default=10240, ge=256, le=102400)
    timeout_seconds: int = Field(default=15, ge=1, le=300)

    gpu_policy: GpuPolicy = GpuPolicy.OPTIONAL
    confidence_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_confirmation: Optional[bool] = None     # Override tier default

    # Integrity: SHA-256 hash of the entry_point module file (set at registration)
    module_hash: Optional[str] = None

    @field_validator("tools")
    @classmethod
    def no_duplicate_tool_names(cls, v):
        names = [t.name for t in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate tool names within a single skill manifest")
        return v
