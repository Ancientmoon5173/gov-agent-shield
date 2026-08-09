"""
权限检查模块（安全层包装）。

包装 src/permission/ 核心权限模块，供 SecurityOrchestrator 使用。
支持 single_user / enterprise 双模式，输出与上层调用完全兼容。
"""

from typing import Optional

from src.permission import PermissionChecker as CorePermissionChecker
from src.permission import create_permission_checker as create_core_checker
from src.permission.models import PermissionResult


class PermissionChecker:
    """权限检查器（安全层包装）。"""

    def __init__(self, security_mode: Optional[str] = None):
        self._core = create_core_checker(security_mode=security_mode)

    def check(self, agent_id: str, tool_name: str,
              params: dict = None) -> PermissionResult:
        """检查 Agent 是否有权调用该工具。"""
        return self._core.check(agent_id, tool_name, params)

    def to_policy_dict(self, agent_id: str) -> dict:
        """返回 Agent 权限策略的只读字典（供评分与审计使用）。"""
        return self._core.to_policy_dict(agent_id)

    def calculate_permission_risk(self, context: dict = None) -> float:
        """返回权限风险分（当前预留接口）。"""
        return 0.0

    def check_resource_access(self, resource_path: str, user_role: str = "") -> dict:
        """资源访问校验（当前预留接口）。"""
        return {"allowed": True, "reason": "权限校验通过（预留）"}

    def approve(self, approval_id: str) -> bool:
        """审批通过。"""
        return self._core.approve(approval_id)

    def reject(self, approval_id: str) -> bool:
        """拒绝审批。"""
        return self._core.reject(approval_id)

    def get_approval_status(self, approval_id: str) -> str:
        """查看审批状态。"""
        return self._core.get_approval_status(approval_id)


def create_permission_checker(security_mode: Optional[str] = None) -> PermissionChecker:
    """创建权限检查器实例。"""
    return PermissionChecker(security_mode=security_mode)
