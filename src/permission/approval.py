"""
审批管理器（轻量级，内存实现）。

不依赖数据库，使用内存字典管理审批状态。
适用于 Demo 和 MVP 阶段。
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class ApprovalManager:
    """审批管理器。"""

    def __init__(self):
        self._approvals: Dict[str, Dict[str, Any]] = {}
        self._counter = 0

    def request(self, agent_id: str, tool_name: str,
                params: dict = None, reason: str = "") -> str:
        """
        发起审批请求。

        Returns:
            approval_id: 审批请求 ID
        """
        self._counter += 1
        approval_id = f"AP-{self._counter:04d}"
        self._approvals[approval_id] = {
            "id": approval_id,
            "agent_id": agent_id,
            "tool_name": tool_name,
            "params": params or {},
            "reason": reason,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
        }
        return approval_id

    def approve(self, approval_id: str) -> bool:
        """审批通过。"""
        approval = self._approvals.get(approval_id)
        if not approval or approval["status"] != "pending":
            return False
        approval["status"] = "approved"
        approval["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def reject(self, approval_id: str) -> bool:
        """审批拒绝。"""
        approval = self._approvals.get(approval_id)
        if not approval or approval["status"] != "pending":
            return False
        approval["status"] = "rejected"
        approval["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def check(self, approval_id: str) -> str:
        """查询审批状态。返回 pending / approved / rejected / not_found。"""
        approval = self._approvals.get(approval_id)
        if not approval:
            return "not_found"
        return approval["status"]

    def get_pending(self) -> list:
        """获取所有待审批请求。"""
        return [a for a in self._approvals.values()
                if a["status"] == "pending"]

    def get_all(self) -> list:
        """获取所有审批记录。"""
        return list(self._approvals.values())


def create_approval_manager() -> ApprovalManager:
    """创建审批管理器实例。"""
    return ApprovalManager()
