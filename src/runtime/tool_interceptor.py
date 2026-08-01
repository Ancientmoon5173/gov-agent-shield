
"""
ToolInterceptor — 工具调用安全拦截器。

接收任意 Agent 产生的 Tool Call，交由 SecurityOrchestrator 检查。
根据检查结果决定：放行 / 阻断 / 熔断 / 审批。
"""

from typing import Dict, Any, Optional

from src.security import create_orchestrator
from .tool_request import ToolRequest


class ToolInterceptor:
    """工具调用拦截器。"""

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator or create_orchestrator()

    def intercept(self, request: ToolRequest) -> Dict[str, Any]:
        """
        拦截一次工具调用并执行安全检查。

        Args:
            request: ToolRequest 工具调用请求

        Returns:
            {
                "decision": "allow" | "block" | "kill" | "review",
                "reason": str,
                "security_result": dict,
            }
        """
        # 调用 SecurityOrchestrator 检查
        result = self.orchestrator.check_tool_call(
            session_id=request.session_id,
            tool_name=request.tool_name,
            params=request.parameters,
            agent_id=request.agent_id,
        )

        action = result.get("action", "allow")

        if action in ("allow", "warn"):
            decision = "allow"
        elif action == "review":
            decision = "review"
        else:
            # block / kill
            decision = action

        return {
            "decision": decision,
            "reason": result.get("reason", ""),
            "security_result": result,
        }
