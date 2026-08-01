
"""
Agent 适配器接口。

为不同 LLM Agent（DeepSeek / OpenAI / Codex 等）提供统一接入接口。
Mock 适配器使用 AgentPlanner 模拟 LLM 工具调用。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .tool_request import ToolRequest


class BaseAgentAdapter(ABC):
    """Agent 适配器基类。"""

    @abstractmethod
    def generate_tool_call(self, user_input: str,
                            context: Optional[Dict[str, Any]] = None) -> ToolRequest:
        """根据用户输入生成工具调用请求。"""
        pass

    @abstractmethod
    def generate_response(self, user_input: str, tool_results: Any,
                          context: Optional[Dict[str, Any]] = None) -> str:
        """根据工具结果生成最终回复。"""
        pass


class MockAgentAdapter(BaseAgentAdapter):
    """Mock 适配器：使用 AgentPlanner 模拟 LLM 工具调用。"""

    def __init__(self, agent_id: str = "default_agent"):
        from src.agent.planner import create_planner
        self.planner = create_planner()
        self.agent_id = agent_id

    def generate_tool_call(self, user_input: str,
                            context: Optional[Dict[str, Any]] = None) -> ToolRequest:
        context = context or {}
        tc = self.planner.plan(user_input)
        return ToolRequest(
            session_id=context.get("session_id", "unknown"),
            agent_id=self.agent_id,
            tool_name=tc.tool_name,
            parameters=tc.parameters,
            context=context,
        )

    def generate_response(self, user_input: str, tool_results: Any,
                          context: Optional[Dict[str, Any]] = None) -> str:
        return str(tool_results)


class CodexAdapter(BaseAgentAdapter):
    """Codex / OpenAI 兼容适配器（真实 LLM 接入示例）。

    通过 OpenAI 兼容接口连接 DeepSeek / OpenAI / 通义千问等。
    接入时配置 API Key 后启用。
    """

    def __init__(self, agent_id: str = "codex_agent"):
        self.agent_id = agent_id
        self.llm = None  # 预留：初始化 ChatOpenAI

    def generate_tool_call(self, user_input: str,
                            context: Optional[Dict[str, Any]] = None) -> ToolRequest:
        raise NotImplementedError("真实 LLM 接入待配置 API Key")

    def generate_response(self, user_input: str, tool_results: Any,
                          context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("真实 LLM 接入待配置 API Key")
