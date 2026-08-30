from enum import Enum
from typing import Dict, Any, Callable, List, Optional
from pydantic import BaseModel, Field

class RiskTier(int, Enum):
    TIER_0 = 0 # Local reasoning, response formatting
    TIER_1 = 1 # Read-only, low-sensitivity telemetry
    TIER_2 = 2 # Read approved user-selected workspace content
    TIER_3 = 3 # Create/modify files, launch known apps
    TIER_4 = 4 # Delete data, security settings, credentials

class ToolSchema(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str
    risk_tier: RiskTier
    parameters: Dict[str, Any]
    required_capabilities: List[str] = []
    
class ToolDefinition(BaseModel):
    tool_schema: ToolSchema
    executor: Callable

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        
    def register(self, tool_def: ToolDefinition):
        self.tools[tool_def.tool_schema.name] = tool_def
        
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self.tools.get(name)
        
    def get_schemas_for_llm(self) -> str:
        prompt = "Tools available:\n"
        for name, tool in self.tools.items():
            params = []
            for param_name, param_info in tool.tool_schema.parameters.items():
                params.append(f"{param_name}: {param_info.get('type', 'string')}")
            param_str = ", ".join(params)
            prompt += f"- {name}({param_str}): {tool.tool_schema.description}\n"
        prompt += (
            "To use a tool, you MUST output a JSON block wrapped in <tool_call> tags. Example:\n"
            '<tool_call>{"name": "search_web", "args": {"query": "current weather"}}</tool_call>\n'
        )
        return prompt

tool_registry = ToolRegistry()
