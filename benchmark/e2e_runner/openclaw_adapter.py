"""
OpenClaw Plugin 契约适配层。

模拟 OpenClaw before_tool_call 生成的 ToolRequest，
并通过 FastAPI /security/check_tool 走真实 HTTP 安全决策链路。
"""

from typing import Any, Dict


def build_tool_request(
    session_id: str,
    agent_id: str,
    tool_name: str,
    parameters: Dict[str, Any],
    task_context: Dict[str, Any],
    timestamp: str,
) -> Dict[str, Any]:
    """按 OpenClaw 插件 ToolRequest 契约构造请求。"""
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "parameters": parameters,
        "context": {
            "run_id": f"e2e-{session_id}",
            "tool_call_id": f"call-{tool_name}",
            "channel_id": "benchmark",
        },
        "task_context": task_context,
        "timestamp": timestamp,
    }


def send_tool_request(client, request: Dict[str, Any]) -> Dict[str, Any]:
    """模拟插件 HTTP 调用 /security/check_tool。"""
    response = client.post("/security/check_tool", json=request)
    response.raise_for_status()
    return response.json()
