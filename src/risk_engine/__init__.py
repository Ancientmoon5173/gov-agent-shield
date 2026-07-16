"""
风险评分与处置模块。

综合多个检测源的评分，决定放行/审批/阻断/熔断。
"""

from .scorer import RiskScorer
from .actions import RiskAction, DispositionEngine

__all__ = ["RiskScorer", "RiskAction", "DispositionEngine"]
