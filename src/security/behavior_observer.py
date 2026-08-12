"""
行为特征观察器（Behavior Observer，方案 B）。

只观察、不阻断：当工具调用命中敏感资产与虚拟规则时，输出
低权重风险信号，供审计与会话风险提升参考。

设计约束：
- risk_increment 保持低权重（默认 0.05），避免误报放大
- 最终决策仍由 BehaviorAnalyzer + RiskEngine 决定
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config import DECOY_VIRTUAL_RULES_PATH


DEFAULT_RISK_INCREMENT = 0.05


class BehaviorObserver:
    """行为特征观察器。"""

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None):
        self.rules = rules if rules is not None else self._load_rules()

    def _load_rules(self) -> List[Dict[str, Any]]:
        path = Path(DECOY_VIRTUAL_RULES_PATH)
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return list(data.get("rules", []))
        except (json.JSONDecodeError, OSError):
            return []

    def observe(
        self,
        tool_name: str,
        params: Dict[str, Any],
        asset_context: Dict[str, Any],
        prior_hits: int = 0,
    ) -> Dict[str, Any]:
        """
        观察一次工具调用。

        Returns:
            {
                "virtual_hit": bool,
                "confidence": float,
                "risk_increment": float,
                "rule_id": str,
            }
        """
        if not asset_context.get("matched"):
            return {
                "virtual_hit": False,
                "confidence": 0.0,
                "risk_increment": 0.0,
                "rule_id": "",
            }

        text = self._collect_text(params)
        sensitivity = str(asset_context.get("sensitivity", "LOW"))

        for rule in self.rules:
            target_tools = rule.get("target_tools", [])
            if tool_name not in target_tools:
                continue

            patterns = rule.get("patterns", [])
            if not any(str(p).lower() in text.lower() for p in patterns):
                continue

            min_sensitivity = str(rule.get("min_sensitivity", "MEDIUM"))
            if self._sensitivity_rank(sensitivity) < self._sensitivity_rank(min_sensitivity):
                continue

            base = float(rule.get("base_confidence", 0.3))
            confidence = min(base + (0.1 if prior_hits >= 1 else 0.0), 0.9)
            return {
                "virtual_hit": True,
                "confidence": round(confidence, 3),
                "risk_increment": float(
                    rule.get("risk_increment", DEFAULT_RISK_INCREMENT)
                ),
                "rule_id": str(rule.get("rule_id", "")),
            }

        return {
            "virtual_hit": False,
            "confidence": 0.0,
            "risk_increment": 0.0,
            "rule_id": "",
        }

    def _sensitivity_rank(self, level: str) -> int:
        return {
            "LOW": 0,
            "MEDIUM": 1,
            "SENSITIVE": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }.get(level.upper(), 0)

    def _collect_text(self, params: Dict[str, Any]) -> str:
        parts = []
        for value in params.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if isinstance(v, str))
        return " ".join(parts)


def create_behavior_observer() -> BehaviorObserver:
    """创建行为特征观察器。"""
    return BehaviorObserver()
