"""
输入检测引擎。

核心检测逻辑：对输入的文本进行多层扫描，判断是否存在攻击。
"""

from typing import List, Dict, Any


class InputDetector:
    """输入安全检测器。"""

    def __init__(self):
        self.rules = []

    def add_rule(self, rule: Any) -> None:
        """添加一条检测规则。"""
        self.rules.append(rule)

    def scan(self, text: str) -> Dict[str, Any]:
        """
        扫描输入文本，返回检测结果。

        返回格式:
        {
            "is_attack": bool,      # 是否检测到攻击
            "risk_score": float,    # 风险评分 0-1
            "findings": [           # 具体的检测发现
                {
                    "type": str,    # 攻击类型
                    "detail": str,  # 检测详情
                    "position": int # 文本位置
                }
            ]
        }
        """
        findings = []

        for rule in self.rules:
            result = rule.match(text)
            if result:
                findings.append(result)

        # 综合评分：取所有发现中最高分
        risk_score = max(
            (f.get("score", 0) for f in findings),
            default=0.0,
        )

        return {
            "is_attack": risk_score > 0.5,
            "risk_score": risk_score,
            "findings": findings,
        }

    def scan_multi(self, texts: List[str]) -> List[Dict[str, Any]]:
        """批量扫描多个文本。"""
        return [self.scan(t) for t in texts]
