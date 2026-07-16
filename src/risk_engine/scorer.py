"""
风险评分引擎。
综合输入检测、工具调用监控、诱饵监控等来源评分。
"""

from typing import List, Dict, Any

class RiskScorer:
    WEIGHTS = {"input_guard": 0.30, "tool_gateway": 0.30, "decoy_monitor": 0.25, "sensitive_data": 0.15}

    def __init__(self):
        self.scores: Dict[str, float] = {}
        self.events: List[Dict[str, Any]] = []

    def add_score(self, source: str, score: float, detail: str = ""):
        self.scores[source] = max(self.scores.get(source, 0), score)
        self.events.append(dict(source=source, score=score, detail=detail))

    def calculate(self):
        if not self.scores:
            return dict(total_score=0.0, max_score=0.0, weighted_score=0.0, sources={}, level="LOW", events=[])
        total_weight = 0
        weighted_sum = 0
        for source, score in self.scores.items():
            weight = self.WEIGHTS.get(source, 0.1)
            weighted_sum += score * weight
            total_weight += weight
        weighted_score = weighted_sum / total_weight if total_weight > 0 else 0
        max_score = max(self.scores.values())
        total_score = max(weighted_score, max_score * 0.8)
        if total_score >= 0.8: level = "CRITICAL"
        elif total_score >= 0.6: level = "HIGH"
        elif total_score >= 0.3: level = "MEDIUM"
        else: level = "LOW"
        return dict(total_score=round(total_score, 3), max_score=round(max_score, 3), weighted_score=round(weighted_score, 3), sources=dict(self.scores), level=level, events=self.events)

    def reset(self):
        self.scores.clear()
        self.events.clear()
