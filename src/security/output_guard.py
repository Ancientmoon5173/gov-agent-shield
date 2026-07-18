"""
输出检测与脱敏模块。

检测 Agent 输出中的敏感数据：
- 身份证号（完整）
- 手机号（完整）
- API Key / Token / 密码
- 内部机密文件标记
"""

import re
from typing import Dict, Any, List


class OutputGuard:
    """输出安全检测器。"""

    # 敏感数据正则模式
    PATTERNS = {
        "id_card": {
            "pattern": r"[1-9][0-9]{5}(19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{3}[0-9Xx]",
            "risk_score": 0.9,
            "label": "身份证号",
        },
        "phone": {
            "pattern": r"1[3-9][0-9]{9}",
            "risk_score": 0.8,
            "label": "手机号",
        },
        "api_key": {
            "pattern": r"(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|api[_-]?key[_-]?[=:][a-zA-Z0-9]{16,})",
            "risk_score": 0.95,
            "label": "API Key / Token",
        },
        "bank_card": {
            "pattern": r"[0-9]{16,19}",
            "risk_score": 0.85,
            "label": "银行账号",
        },
    }

    # 内部文件标记关键词
    INTERNAL_MARKERS = [
        "内部文件", "机密", "绝密", "秘密",
        "internal", "confidential", "secret",
        "仅内部使用", "未经授权不得",
    ]

    def __init__(self):
        self._compiled = {}
        for name, cfg in self.PATTERNS.items():
            self._compiled[name] = re.compile(cfg["pattern"])

    def scan(self, text: str) -> Dict[str, Any]:
        """
        扫描输出文本中的敏感数据。

        Returns:
            {
                "has_sensitive_data": bool,
                "risk_score": float,
                "findings": [
                    {"type": str, "label": str, "risk_score": float, "position": int}
                ]
            }
        """
        findings = []
        max_risk = 0.0

        for name, compiled in self._compiled.items():
            matches = compiled.finditer(text)
            for match in matches:
                cfg = self.PATTERNS[name]
                findings.append({
                    "type": name,
                    "label": cfg["label"],
                    "risk_score": cfg["risk_score"],
                    "position": match.start(),
                    "matched": match.group()[:20],
                })
                max_risk = max(max_risk, cfg["risk_score"])

        # 检测内部文件标记
        for marker in self.INTERNAL_MARKERS:
            if marker in text:
                findings.append({
                    "type": "internal_marker",
                    "label": "内部文件标记",
                    "risk_score": 0.7,
                    "position": text.find(marker),
                    "matched": marker,
                })
                max_risk = max(max_risk, 0.7)
                break

        return {
            "has_sensitive_data": len(findings) > 0,
            "risk_score": max_risk,
            "findings": findings,
        }

    def mask_sensitive(self, text: str, types: List[str] = None) -> str:
        """
        对输出文本中的敏感数据做脱敏处理。

        Args:
            text: 原始文本
            types: 要脱敏的数据类型列表（None=全部）

        Returns:
            脱敏后的文本
        """
        if types is None:
            types = list(self.PATTERNS.keys())

        result = text
        for name in types:
            if name not in self._compiled:
                continue
            cfg = self.PATTERNS[name]
            compiled = self._compiled[name]

            def mask_match(m, label=cfg["label"]):
                matched = m.group()
                if len(matched) <= 4:
                    return "****"
                return matched[:4] + "****" + matched[-4:]

            result = compiled.sub(mask_match, result)

        return result


def create_output_guard() -> OutputGuard:
    """创建输出检测器实例。"""
    return OutputGuard()
