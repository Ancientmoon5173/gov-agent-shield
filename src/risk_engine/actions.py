"""
处置动作引擎。根据风险评分决定放行/审批/阻断/熔断。
"""

from enum import Enum
from typing import Dict, Any
from src.config import RISK_THRESHOLD_LOW, RISK_THRESHOLD_MEDIUM, RISK_THRESHOLD_HIGH

class RiskAction(Enum):
    ALLOW = "allow"
    REVIEW = "review"
    WARN = "warn"
    BLOCK = "block"
    KILL = "kill"

class DispositionEngine:
    def decide(self, risk_result: Dict[str, Any]) -> Dict[str, Any]:
        total_score = risk_result.get("total_score", 0)
        level = risk_result.get("level", "LOW")
        if total_score >= RISK_THRESHOLD_HIGH or level == "CRITICAL":
            return dict(action="kill", action_name="熔断", reason="高风险行为，已自动熔断任务", risk_level=level, risk_score=total_score)
        elif total_score >= RISK_THRESHOLD_MEDIUM or level == "HIGH":
            return dict(action="block", action_name="阻断", reason="高风险操作，已阻断", risk_level=level, risk_score=total_score)
        elif total_score >= RISK_THRESHOLD_LOW or level == "MEDIUM":
            return dict(action="review", action_name="审批", reason="可疑行为，需要人工确认", risk_level=level, risk_score=total_score)
        else:
            return dict(action="allow", action_name="放行", reason="安全检测通过", risk_level=level, risk_score=total_score)
