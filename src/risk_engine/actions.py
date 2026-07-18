"""
处置动作引擎。5级风险处置：放行/告警/审批/阻断/熔断。
"""

from enum import Enum
from typing import Dict, Any
from src.config import RISK_LEVEL_THRESHOLDS

class RiskAction(Enum):
    ALLOW = "allow"
    WARN = "warn"
    REVIEW = "review"
    BLOCK = "block"
    KILL = "kill"

class DispositionEngine:
    def decide(self, risk_result: Dict[str, Any]) -> Dict[str, Any]:
        level = risk_result.get("level", "LOW")
        if level == "CRITICAL":
            return dict(action="kill", action_name="熔断", reason="检测到严重安全攻击，已终止整个任务",
                        risk_level=level, risk_score=risk_result.get("total_score", 0))
        elif level == "VERY_HIGH":
            return dict(action="block", action_name="阻断", reason="检测到高风险操作，已阻断",
                        risk_level=level, risk_score=risk_result.get("total_score", 0))
        elif level == "HIGH":
            return dict(action="review", action_name="审批", reason="检测到可疑行为，需要人工确认",
                        risk_level=level, risk_score=risk_result.get("total_score", 0))
        elif level == "MEDIUM":
            return dict(action="warn", action_name="告警", reason="检测到低风险行为，已记录",
                        risk_level=level, risk_score=risk_result.get("total_score", 0))
        else:
            return dict(action="allow", action_name="放行", reason="安全检测通过",
                        risk_level=level, risk_score=risk_result.get("total_score", 0))
