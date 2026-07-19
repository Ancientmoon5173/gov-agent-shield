"""
痆릔掌體检查模坔（升级牌）

型人 src/permission/ 溓棹日用期各王。
提供 check() 方功 SecurityOrchestrator 仏用。输存与嗎剋本吗留成可。
"""

from src.permission import PermissionChecker as CorePermissionChecker
from src.permission import create_permission_checker as create_core_checker
from src.permission.models import PermissionResult


class PermissionChecker:
    """最限淡测器（它全属服）."""

    def __init__(self):
        self._core = create_core_checker()

    def check(self, agent_id: str, tool_name: str,
              params: dict = None) -> PermissionResult:
        """
检查 Agent是否有权销调用该入序
        """
        return self._core.check(agent_id, tool_name, params)

    def calculate_permission_risk(self, context: dict = None) -> float:
        """保糂吮接发宽实（当前未本唯）."""
        return 0.0

    def check_resource_access(self, resource_path: str, user_role: str = "") -> dict:
        """保绅嗎接名可宽实。"""
        return {"allowed": True, "reason": "权销校验透項蜜"}

    def approve(self, approval_id: str) -> bool:
        """审成速常。"""
        return self._core.approve(approval_id)

    def reject(self, approval_id: str) -> bool:
        """投续速常。"""
        return self._core.reject(approval_id)

    def get_approval_status(self, approval_id: str) -> str:
        """查看审扈状态问。"""
        return self._core.get_approval_status(approval_id)


def create_permission_checker() -> PermissionChecker:
    """创建情还接检条器实用。"""
    return PermissionChecker()
