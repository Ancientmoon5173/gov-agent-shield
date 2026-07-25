
from typing import Dict, Any
from dataclasses import dataclass, field, asdict


@dataclass
class ToolCall:
    """
    Agent Planner 的输出：模拟 LLM 的工具调用决策。
    
    Attributes:
        tool_name: 工具名称（"" 表示无需调用工具）
        parameters: 工具参数字典
        reasoning: 决策理由（供 UI 展示）
    """
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.tool_name,
            "parameters": self.parameters,
            "reasoning": self.reasoning,
        }

    def is_valid(self) -> bool:
        return bool(self.tool_name)
