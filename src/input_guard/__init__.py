"""
输入安全检测模块。

负责检测用户输入、文档内容中的 Prompt 注入、越狱攻击和指令覆盖。
"""

from .detector import InputDetector
from .rules import InjectionRule

__all__ = ["InputDetector", "InjectionRule"]
