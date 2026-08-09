"""
数据分类器（DataClassifier）。

对工具调用涉及的数据进行分级：
PUBLIC / INTERNAL / SENSITIVE / CRITICAL。

职责边界：
- 只做数据分级，不负责权限判断
- 只输出风险上下文，不负责阻断
- 分级结果作为 tool risk 的修正因素进入 RiskScorer
"""

from typing import Dict, Any, List

from src.config import DATA_CLASS_RULES


class DataClassifier:
    """数据分类器。"""

    def __init__(self, rules: Dict[str, Any] = None):
        self.rules = rules or DATA_CLASS_RULES

    def classify(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        对工具调用涉及的数据进行分级。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            {
                "data_class": "PUBLIC" | "INTERNAL" | "SENSITIVE" | "CRITICAL",
                "risk_score": float,
                "findings": [str],
            }
        """
        params = params or {}
        text = self._collect_text(params)
        path = str(params.get("file_path", "") or params.get("path", ""))
        findings: List[str] = []

        for level in ("CRITICAL", "SENSITIVE", "INTERNAL"):
            cfg = self.rules[level]
            matched_keywords = [
                kw for kw in cfg.get("keywords", [])
                if kw.lower() in text.lower()
            ]
            matched_path = [
                marker for marker in cfg.get("path_markers", [])
                if marker.lower() in path.lower()
            ]
            if matched_keywords or matched_path:
                if matched_keywords:
                    findings.append(
                        f"{level}: 命中关键词 {','.join(matched_keywords)}"
                    )
                if matched_path:
                    findings.append(
                        f"{level}: 路径含 {','.join(matched_path)}"
                    )
                return {
                    "data_class": level,
                    "risk_score": float(cfg.get("risk_score", 0.0)),
                    "findings": findings,
                }

        return {
            "data_class": "PUBLIC",
            "risk_score": 0.0,
            "findings": [],
        }

    def _collect_text(self, params: Dict[str, Any]) -> str:
        """收集所有参数文本用于关键词匹配。"""
        parts = []
        for value in params.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if isinstance(v, str))
        return " ".join(parts)


def create_data_classifier() -> DataClassifier:
    """创建数据分类器实例。"""
    return DataClassifier()
