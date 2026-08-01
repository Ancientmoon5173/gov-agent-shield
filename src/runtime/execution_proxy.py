
"""
ExecutionProxy — 工具执行代理。

仅在安全层放行后执行工具调用。
所有工具执行必须经过此代理，禁止直接调用。
"""

from typing import Dict, Any, Optional

# Lazy import GOV_TOOLS in __init__ to avoid circular dependency


class ExecutionProxy:
    """工具执行代理。"""

    def __init__(self, tools=None):
        if tools is None:
            from src.agent.tools import GOV_TOOLS
            tools = GOV_TOOLS
        self.tools = {t.name: t for t in tools}

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """执行工具（仅当安全层放行后调用）。"""
        tool = self.tools.get(tool_name)
        if not tool:
            return f"工具不存在: {tool_name}"
        try:
            return str(tool.invoke(parameters))
        except Exception as e:
            return f"工具执行失败: {str(e)}"

    def get_available_tools(self) -> list:
        """获取可用工具列表。"""
        return list(self.tools.keys())
