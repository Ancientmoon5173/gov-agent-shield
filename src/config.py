"""
全局配置模块。

所有模块共享的配置从这里读取，而不是各自硬编码。
这样做的好处：改一个配置项，所有模块一起生效。
"""

import os
from pathlib import Path

# 项目根目录自动检测
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
AUDIT_DIR = DATA_DIR / "audit_logs"
DECOY_DIR = DATA_DIR / "decoy"

# 确保目录存在
for _dir in [DATA_DIR, AUDIT_DIR, DECOY_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# 数据库
DATABASE_URL = os.getenv(
    "GOVAGENT_DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'govagent_shield.db'}"
)

# 大模型 API 配置
# 默认使用模拟模式，不依赖外部 API
LLM_MOCK_MODE = os.getenv("GOVAGENT_LLM_MOCK", "true").lower() == "true"
LLM_API_KEY = os.getenv("GOVAGENT_LLM_API_KEY", "")
LLM_API_BASE = os.getenv("GOVAGENT_LLM_API_BASE", "https://api.deepseek.com")
LLM_MODEL_NAME = os.getenv("GOVAGENT_LLM_MODEL", "deepseek-chat")

# 安全检测配置
PROMPT_INJECTION_THRESHOLD = float(
    os.getenv("GOVAGENT_INJECTION_THRESHOLD", "0.7")
)
SENSITIVE_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# 保留旧阈值常量（向后兼容）
RISK_THRESHOLD_LOW = 0.3
RISK_THRESHOLD_MEDIUM = 0.6
RISK_THRESHOLD_HIGH = 0.8

# 四维风险融合权重
RISK_WEIGHTS = {
    "R_input": 0.20,
    "R_tool": 0.35,
    "R_output": 0.25,
    "R_behavior": 0.20,
}

# 5级风险阈值
RISK_LEVEL_THRESHOLDS = {
    "LOW": 0.0,
    "MEDIUM": 0.30,
    "HIGH": 0.50,
    "VERY_HIGH": 0.70,
    "CRITICAL": 0.85,
}

# 服务配置
SERVICE_HOST = os.getenv("GOVAGENT_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("GOVAGENT_PORT", "8000"))
