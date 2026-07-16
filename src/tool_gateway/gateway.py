"""
工具调用安全网关。

核心逻辑：当 Agent 想调用某个工具时，先经过网关检查。
"""

from typing import Dict, Any, Optional
from .policies import SecurityPolicy, Action


class ToolGateway:
    """工具调用安全网关。"""

    def __init__(self):
        self.policies: Dict[str, SecurityPolicy] = {}

    def register_policy(self, policy: SecurityPolicy) -> None:
        """注册一条安全策略。"""
        self.policies[policy.name] = policy

    def check(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        检查工具调用是否安全。

        返回:
        {
            "allowed": bool,        # 是否允许调用
            "action": str,          # 处置动作
            "risk_score": float,    # 风险评分
            "reason": str,          # 原因说明
        }
        """
        matched_policy = None

        # 查找匹配的策略
        for policy in self.policies.values():
            if policy.matches(tool_name, params, context):
                matched_policy = policy
                break

        if matched_policy is None:
            # 没有匹配策略：默认放行
            return {
                "allowed": True,
                "action": Action.ALLOW.value,
                "risk_score": 0.0,
                "reason": "No matching policy, allowed by default",
            }

        # 根据策略的判断逻辑
        return matched_policy.evaluate(tool_name, params, context)

    def block(self, tool_name: str, reason: str) -> Dict[str, Any]:
        """主动阻断一次工具调用。"""
        return {
            "allowed": False,
            "action": Action.BLOCK.value,
            "risk_score": 1.0,
            "reason": reason,
        }
