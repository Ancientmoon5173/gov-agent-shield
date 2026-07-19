"""
权限数据结构定义。

包括权限策略和权限检查结果的数据模型。
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class PermissionPolicy:
    """单个 Agent 的权限策略定义。"""
    agent_id: str = "default_agent"
    role: str = "employee"
    allowed_tools: List[str] = field(default_factory=list)
    restricted_tools: List[str] = field(default_factory=list)
    require_approval: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionPolicy":
        return cls(
            agent_id=data.get("id", "default_agent"),
            role=data.get("role", "employee"),
            allowed_tools=data.get("allowed_tools", []),
            restricted_tools=data.get("restricted_tools", []),
            require_approval=data.get("require_approval", []),
        )


@dataclass
class PermissionResult:
    """权限检查结果。"""
    allowed: bool = False
    action: str = "block"       # "allow" / "block" / "review"
    reason: str = ""
    require_approval: bool = False
    approval_id: str = ""
    policy: Optional[PermissionPolicy] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "reason": self.reason,
            "require_approval": self.require_approval,
            "approval_id": self.approval_id,
        }
