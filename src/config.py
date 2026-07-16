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

# 风险评分阈值
RISK_THRESHOLD_LOW = 0.3    # < 0.3: 放行
RISK_THRESHOLD_MEDIUM = 0.6 # 0.3-0.6: 需要审批
RISK_THRESHOLD_HIGH = 0.8   # 0.6-0.8: 告警+审批
                             # > 0.8: 自动阻断

# 服务配置
SERVICE_HOST = os.getenv("GOVAGENT_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("GOVAGENT_PORT", "8000"))
