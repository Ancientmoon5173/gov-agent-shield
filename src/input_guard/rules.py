"""
检测规则定义。

每条规则定义一个攻击模式的检测逻辑。
"""

import re
from typing import Optional, Dict, Any


class InjectionRule:
    """Prompt 注入检测规则。"""

    def __init__(
        self,
        name: str,
        pattern: str,
        attack_type: str,
        severity: float = 0.7,
        description: str = "",
    ):
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.attack_type = attack_type
        self.severity = severity
        self.description = description

    def match(self, text: str) -> Optional[Dict[str, Any]]:
        """
        检查文本是否匹配此规则。

        返回匹配结果，无匹配返回 None。
        """
        match = self.pattern.search(text)
        if match:
            return {
                "rule_name": self.name,
                "type": self.attack_type,
                "detail": self.description,
                "position": match.start(),
                "matched_text": match.group()[:50],
                "score": self.severity,
            }
        return None


# ========================
# 预定义规则
# ========================

# 越狱指令模式
JAILBREAK_RULES = [
    InjectionRule(
        name="jailbreak_role_play",
        pattern=r"(ignore|forget|disregard).{0,20}(previous|all|above|prior)",
        attack_type="jailbreak",
        severity=0.8,
        description="试图覆盖已有指令要求",
    ),
    InjectionRule(
        name="jailbreak_act_as",
        pattern=r"act\s+as\s+(if|though|now|a\s+different)",
        attack_type="jailbreak",
        severity=0.7,
        description="试图让模型扮演与系统设定冲突的角色",
    ),
    InjectionRule(
        name="jailbreak_dan",
        pattern=r"(DAN|do\s+anything\s+now|unlimited|no\s+rules)",
        attack_type="jailbreak",
        severity=0.9,
        description="典型的'Do Anything Now'越狱模式",
    ),
]

# 指令覆盖模式
OVERRIDE_RULES = [
    InjectionRule(
        name="override_end",
        pattern=r"end\s+(conversation|session|chat|task)",
        attack_type="command_override",
        severity=0.6,
        description="试图提前终止正常流程",
    ),
    InjectionRule(
        name="override_injection",
        pattern=r"(\"{3}|'{3}).{0,100}(system|instruction|prompt)",
        attack_type="command_override",
        severity=0.8,
        description="试图注入新的系统指令",
    ),
]

# 敏感指令模式
SENSITIVE_COMMAND_RULES = [
    InjectionRule(
        name="sensitive_read_file",
        pattern=r"(read|open|access|get).{0,20}(file|document|contract|secret)",
        attack_type="sensitive_request",
        severity=0.5,
        description="请求访问可能受限的文件",
    ),
    InjectionRule(
        name="sensitive_exfiltrate",
        pattern=r"(send|upload|post|exfiltrate|leak).{0,20}(to|via|through)",
        attack_type="data_exfiltration",
        severity=0.85,
        description="试图向外发送数据",
    ),
]

# 合并所有规则
DEFAULT_RULES = JAILBREAK_RULES + OVERRIDE_RULES + SENSITIVE_COMMAND_RULES


def get_default_detector():
    """创建一个配置好默认规则的检测器。"""
    from .detector import InputDetector

    detector = InputDetector()
    for rule in DEFAULT_RULES:
        detector.add_rule(rule)
    return detector
