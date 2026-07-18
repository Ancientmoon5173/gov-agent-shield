"""
处置动作引擎。5级风险处置 + DecoyTriggered诱饵策略。
"""

from enum import Enum
from typing import Dict, Any


class RiskAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    REVIEW = "review"
    BLOCK = "block"
    KILL = "kill"


class DispositionEngine:
    """处置决策引擎，含DecoyTriggered策略。"""

    def decide(self, risk_result: Dict[str, Any],
               decoy_context: Dict[str, Any] = None) -> Dict[str, Any]:
        r_decoy = 0.0
        decoy_triggered = False
        if decoy_context and decoy_context.get("triggered"):
            r_decoy = decoy_context.get("risk_score", 0.0)
            decoy_triggered = True

        if decoy_triggered and r_decoy > 0:
            return self._decoy_strategy(decoy_context)

        return self._default_strategy(risk_result)

    def _decoy_strategy(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        detail = ctx.get("detail", "")
        resource = ctx.get("resource", "")
        has_upload = ctx.get("has_upload_context", False)
        authorized = ctx.get("is_authorized", False)

        if authorized:
            return dict(action="review", action_name="审批",
                        reason=f"授权用户访问诱饵资源: {resource}",
                        risk_level="VERY_HIGH", risk_score=0.85, decoy_triggered=True)
        if has_upload:
            return dict(action="kill", action_name="熔断",
                        reason=f"诱饵碰触+外传行为: {detail}",
                        risk_level="CRITICAL", risk_score=1.0, decoy_triggered=True)
        return dict(action="block", action_name="阻断",
                    reason=f"访问诱饵敏感资源: {detail}",
                    risk_level="CRITICAL", risk_score=1.0, decoy_triggered=True)

    def _default_strategy(self, risk: Dict[str, Any]) -> Dict[str, Any]:
        score = risk.get("total_score", 0)
        level = risk.get("level", "LOW")
        if level == "CRITICAL":
            return dict(action="kill", action_name="熔断", reason="严重安全攻击，已终止", risk_level=level, risk_score=score, decoy_triggered=False)
        elif level == "VERY_HIGH":
            return dict(action="block", action_name="阻断", reason="高风险操作，已阻断", risk_level=level, risk_score=score, decoy_triggered=False)
        elif level == "HIGH":
            return dict(action="review", action_name="审批", reason="可疑行为，需要确认", risk_level=level, risk_score=score, decoy_triggered=False)
        elif level == "MEDIUM":
            return dict(action="warn", action_name="告警", reason="低风险行为，已记录", risk_level=level, risk_score=score, decoy_triggered=False)
        else:
            return dict(action="allow", action_name="放行", reason="安全检测通过", risk_level=level, risk_score=score, decoy_triggered=False)
