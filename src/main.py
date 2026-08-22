"""
GovAgent-Shield 后端入口。

启动 FastAPI 服务，挂载 Agent 运行和安全检测路由。
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import SERVICE_HOST, SERVICE_PORT
from src.agent import GovAgent, GOV_TOOLS
from src.security import create_orchestrator

# 创建 FastAPI 应用实例
app = FastAPI(
    title="GovAgent-Shield API",
    description="面向政企场景的大模型智能体安全防护平台\n当前阶段：Agent 基础功能已就绪",
    version="0.1.0",
)

# 全局 Agent 实例
_agent: GovAgent = None

def get_agent() -> GovAgent:
    global _agent
    if _agent is None:
        _agent = GovAgent(mode="planner")
    return _agent


# ========================
# 请求/响应模型
# ========================

class AgentRunRequest(BaseModel):
    user_input: str
    session_id: str = ""
    mode: str = "mock"


class AgentRunResponse(BaseModel):
    session_id: str
    user_input: str
    agent_response: str
    trace: list = []
    risk_assessment: dict = {}
    tool_call: dict = {}
    security_result: dict = {}


class SecurityCheckRequest(BaseModel):
    """OpenClaw 适配层安全检测请求。"""
    session_id: str
    agent_id: str = "default_agent"
    tool_name: str
    parameters: dict = {}
    context: dict = {}
    timestamp: str = ""
    task_context: dict = {}


class SecurityOutputCheckRequest(BaseModel):
    """OpenClaw 适配层输出安全检测请求。"""
    tool_name: str
    output_text: str
    session_id: str = ""
    context: dict = {}


# ========================
# 根路径
# ========================

@app.get("/")
def root():
    """根路径，返回系统状态。"""
    return {
        "service": "GovAgent-Shield",
        "status": "running",
        "version": "0.1.0",
        "agent_mode": get_agent().mode,
        "tools_available": len(GOV_TOOLS),
    }


@app.get("/health")
def health():
    """健康检查接口。"""
    return {"status": "healthy"}


# ========================
# Agent API
# ========================

@app.post("/agent/run", response_model=AgentRunResponse)
def agent_run(req: AgentRunRequest):
    """
    执行 Agent 任务。
    接收用户输入，Agent 分析意图并调用工具，返回执行结果。
    """
    agent = get_agent()
    result = agent.run(
        user_input=req.user_input,
        session_id=req.session_id or None,
    )
    return AgentRunResponse(**result)


@app.get("/agent/tools")
def agent_tools():
    """获取 Agent 可用的工具列表。"""
    agent = get_agent()
    tools = agent.get_available_tools()
    return {"total": len(tools), "tools": tools}


@app.get("/agent/sessions/{session_id}")
def agent_session(session_id: str):
    """获取指定会话的历史记录。"""
    agent = get_agent()
    history = agent.get_session_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session_id,
        "total_messages": len(history),
        "history": history,
    }


# ========================
# 安全状态 API
# ========================

_security_orchestrator = None

def get_security_orchestrator():
    global _security_orchestrator
    if _security_orchestrator is None:
        _security_orchestrator = create_orchestrator()
    return _security_orchestrator


@app.get("/security/status")
def security_status():
    """
    获取安全层状态和事件摘要。
    """
    orch = get_security_orchestrator()
    summary = orch.get_security_summary()
    return {
        "status": "active",
        "summary": summary,
    }


@app.get("/security/events/{session_id}")
def security_session_events(session_id: str):
    """
    获取指定会话的安全事件记录。
    """
    orch = get_security_orchestrator()
    events = orch.get_session_events(session_id)
    return {
        "session_id": session_id,
        "total_events": len(events),
        "events": events,
    }


@app.post("/security/check_tool")
def security_check_tool(req: SecurityCheckRequest):
    """
    OpenClaw 适配层安全检测接口。

    接收 OpenClaw ToolCall 的 ToolRequest，调用 SecurityOrchestrator
    进行安全检查，返回 allow / block / kill / review 决策。
    """
    orch = get_security_orchestrator()
    result = orch.check_tool_call(
        session_id=req.session_id,
        tool_name=req.tool_name,
        params=req.parameters,
        agent_id=req.agent_id,
        task_context=req.task_context,
    )
    # 补充决策字段（OpenClaw 侧需要）
    result.setdefault("defense_stage", "risk_engine")
    result.setdefault("decision_reason", result.get("reason", ""))
    return result


@app.post("/security/check_output")
def security_check_output(req: SecurityOutputCheckRequest):
    """
    OpenClaw 适配层输出安全检测接口。

    调用 SecurityOrchestrator.check_output() 检测工具输出中的敏感数据。
    """
    orch = get_security_orchestrator()
    result = orch.check_output(
        session_id=req.session_id or "default",
        tool_name=req.tool_name,
        output_text=req.output_text,
    )
    return result


if __name__ == "__main__":

    uvicorn.run(
        "src.main:app",
        host=SERVICE_HOST,
        port=SERVICE_PORT,
        reload=True,
    )
