"""
Input Risk Context —— 输入风险上下文。

职责：保存一次会话中的输入风险信息，作为 Runtime 风险链路的
风险上下文（R_input 增强），不直接承担阻断决策。

结构：
{
    source: "user_input" | "document_context",
    risk_type: "prompt_injection" | "data_poisoning"
              | "jailbreak" | "sensitive_instruction",
    risk_score: float,
    findings: [str],
}
"""

from typing import Dict, Any, List


class InputRiskContext:
    """输入风险上下文。"""

    def __init__(
        self,
        source: str = "user_input",
        risk_type: str = "input_risk",
        risk_score: float = 0.0,
        findings: List[str] = None,
    ):
        self.source = source
        self.risk_type = risk_type
        self.risk_score = float(risk_score)
        self.findings = findings or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "risk_type": self.risk_type,
            "risk_score": round(self.risk_score, 3),
            "findings": self.findings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InputRiskContext":
        return cls(
            source=str(data.get("source", "user_input")),
            risk_type=str(data.get("risk_type", "input_risk")),
            risk_score=float(data.get("risk_score", 0.0)),
            findings=list(data.get("findings", [])),
        )

    def boost(self) -> float:
        """返回 R_input 增强量：low +0 / medium +0.1 / high +0.2。"""
        if self.risk_score >= 0.7:
            return 0.2
        if self.risk_score >= 0.4:
            return 0.1
        return 0.0


class InputRiskContextStore:
    """会话级输入风险上下文存储（内存）。"""

    def __init__(self):
        self._contexts: Dict[str, InputRiskContext] = {}

    def set(self, session_id: str, context: InputRiskContext) -> None:
        self._contexts[session_id] = context

    def get(self, session_id: str) -> InputRiskContext:
        return self._contexts.get(session_id, InputRiskContext())

    def clear(self, session_id: str) -> None:
        self._contexts.pop(session_id, None)


def create_input_risk_context_store() -> InputRiskContextStore:
    """创建输入风险上下文存储。"""
    return InputRiskContextStore()
