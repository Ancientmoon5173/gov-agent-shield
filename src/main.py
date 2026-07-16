"""
GovAgent-Shield 后端入口。

启动 FastAPI 服务，挂载所有路由。
"""

import uvicorn
from fastapi import FastAPI

from src.config import SERVICE_HOST, SERVICE_PORT

# 创建 FastAPI 应用实例
app = FastAPI(
    title="GovAgent-Shield API",
    description="面向政企场景的大模型智能体安全防护平台",
    version="0.1.0",
)


@app.get("/")
def root():
    """根路径，返回系统状态。"""
    return {
        "service": "GovAgent-Shield",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    """健康检查接口。"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=SERVICE_HOST,
        port=SERVICE_PORT,
        reload=True,
    )
