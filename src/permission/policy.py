"""
权限策略引擎。

负责判断：一个工具调用是否在 Agent 的权限范围内。
"""

from typing import List
from .models import PermissionPolicy


class PolicyEngine:
    """权限策略判断引擎。"""

    def is_tool_allowed(self, policy: PermissionPolicy, tool_name: str) -> bool:
        """
        判断工具是否在允许列表中。

        优先级：
        1. restricted_tools 中有该工具 → 直接禁止
        2. allowed_tools 中有 "*" → 允许全部
        3. allowed_tools 中有该工具 → 允许
        4. 以上都不满足 → 禁止
        """
        # 1. 检查是否在禁止列表
        if tool_name in policy.restricted_tools:
            return False

        # 2. 检查是否允许全部
        if "*" in policy.allowed_tools:
            return True

        # 3. 检查是否在允许列表
        if tool_name in policy.allowed_tools:
            return True

        # 4. 默认禁止
        return False

    def requires_approval(self, policy: PermissionPolicy, tool_name: str) -> bool:
        """判断工具调用是否需要审批。"""
        return tool_name in policy.require_approval

    def get_tool_restriction_reason(self, policy: PermissionPolicy,
                                    tool_name: str) -> str:
        """获取工具被禁止的具体原因。"""
        if tool_name in policy.restricted_tools:
            return f"{tool_name} 被 {policy.agent_id}({policy.role}) 的权限策略列为禁止工具"
        if not self.is_tool_allowed(policy, tool_name):
            return f"{tool_name} 不在 {policy.agent_id}({policy.role}) 的允许工具列表中"
        return ""


def create_policy_engine() -> PolicyEngine:
    """创建策略引擎实例。"""
    return PolicyEngine()
