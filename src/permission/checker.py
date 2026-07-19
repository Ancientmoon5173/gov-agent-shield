"""
权限检查器。

核心逻辑：根据 Agent 身份、工具名和参数，做出权限决策。
输出 ALLOW / BLOCK / REQUIRE_APPROVAL 三种结果。
"""

from typing import Optional
from .models import PermissionPolicy, PermissionResult
from .storage import PermissionStorage, create_permission_storage
from .policy import PolicyEngine, create_policy_engine
from .approval import ApprovalManager


class PermissionChecker:
    """权限检查器。"""

    def __init__(self, storage: Optional[PermissionStorage] = None,
                 policy_engine: Optional[PolicyEngine] = None,
                 approval_manager: Optional[ApprovalManager] = None):
        self.storage = storage or create_permission_storage()
        self.policy_engine = policy_engine or create_policy_engine()
        self.approval_manager = approval_manager or ApprovalManager()

    def check(self, agent_id: str, tool_name: str,
              params: dict = None) -> PermissionResult:
        """
        执行权限检查。

        流程：
        1. 加载 Agent 权限策略
        2. 检查工具是否在禁止列表
        3. 检查工具是否在允许列表
        4. 检查是否需要审批
        5. 返回决策结果
        """
        params = params or {}
        policy = self.storage.get_policy(agent_id)

        # 1. 检查是否在禁止列表
        if tool_name in policy.restricted_tools:
            reason = self.policy_engine.get_tool_restriction_reason(policy, tool_name)
            return PermissionResult(
                allowed=False, action="block", reason=reason, policy=policy,
            )

        # 2. 检查是否在允许列表
        if not self.policy_engine.is_tool_allowed(policy, tool_name):
            reason = self.policy_engine.get_tool_restriction_reason(policy, tool_name)
            return PermissionResult(
                allowed=False, action="block", reason=reason, policy=policy,
            )

        # 3. 检查是否需要审批
        if self.policy_engine.requires_approval(policy, tool_name):
            approval_id = self.approval_manager.request(
                agent_id=agent_id, tool_name=tool_name,
                params=params, reason=f"{tool_name} 需要审批",
            )
            return PermissionResult(
                allowed=False, action="review", reason=f"{tool_name} 需要审批",
                require_approval=True, approval_id=approval_id, policy=policy,
            )

        # 4. 权限通过
        return PermissionResult(
            allowed=True, action="allow", reason="权限检查通过", policy=policy,
        )

    def get_agent_policy(self, agent_id: str) -> PermissionPolicy:
        """获取 Agent 的权限策略。"""
        return self.storage.get_policy(agent_id)

    def list_policies(self) -> list:
        """列出所有可用策略。"""
        return self.storage.list_agents()

    def approve(self, approval_id: str) -> bool:
        """审批通过一个请求。"""
        return self.approval_manager.approve(approval_id)

    def reject(self, approval_id: str) -> bool:
        """拒绝一个请求。"""
        return self.approval_manager.reject(approval_id)

    def get_approval_status(self, approval_id: str) -> str:
        """获取审批状态。"""
        return self.approval_manager.check(approval_id)


def create_permission_checker() -> PermissionChecker:
    """创建权限检查器实例。"""
    return PermissionChecker()
