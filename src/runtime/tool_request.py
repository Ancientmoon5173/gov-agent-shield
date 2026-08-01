
"""
ToolRequest 数据结构。

统一表示任意 Agent 产生的工具调用请求。
"""

from dataclasses import dataclass, field
from typing import Dict, Any
from datetime import datetime


@dataclass
class ToolRequest:
    """工具调用请求。"""
    session_id: str
    agent_id: str
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "context": self.context,
            "timestamp": self.timestamp,
        }
