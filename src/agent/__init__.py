"""
Agent 模块。

定义政企场景下的 AI Agent，支持调用工具和执行任务。
安全层将在后续阶段注入到工具调用链路中。
"""

from .agent import GovAgent
from .tools import GOV_TOOLS

__all__ = ["GovAgent", "GOV_TOOLS"]
