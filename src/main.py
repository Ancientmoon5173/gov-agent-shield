"""
GovAgent-Shield 后端入口。

启动 FastAPI 服务，挂载 Agent 运行和安全检测路由。
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import SERVICE_HOST, SERVICE_PORT
from src.agent import GovAgent, GOV_TOOLS

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
        _agent = GovAgent(mode="mock")
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


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=SERVICE_HOST,
        port=SERVICE_PORT,
        reload=True,
    )
