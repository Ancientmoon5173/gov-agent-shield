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
ASSET_CATALOG_PATH = DATA_DIR / "asset_catalog.json"
DECOY_VIRTUAL_RULES_PATH = DATA_DIR / "decoy_virtual_rules.json"
DECOY_ROUTE_MAPPING_PATH = DATA_DIR / "decoy_route_mapping.json"

# Shadow Decoy（decoy_route）配置
DECOY_ROUTE_CONFIG = {
    "enabled": True,
    "dry_run": (
        os.getenv("GOVAGENT_DECOY_DRY_RUN", "false").lower() == "true"
    ),
    "min_risk_score": 0.7,
    "cooldown_seconds": 300,
    "redirect_tools": ["read", "read_document", "list_directory", "search_files"],
    "target_param": "file_path",
}

# 数据溯源令牌（Data Provenance Token，方案 C 第一阶段）
# 第一阶段只实现外发/写入类工具参数扫描，不做结果注入。
DATA_PROVENANCE_CONFIG = {
    "enabled": True,
    "target_tools": [
        "send_email",
        "http_request",
        "write_file",
        "upload_data",
        "upload_file",
        "exec",
    ],
    "expire_hours": 24,
    "max_injections": 5,
    "leak_action": "block",
    "token_prefix": "DPT",
    "inject_on_sensitive_read": True,
    "inject_tools": ["read", "read_document", "query_citizen_info"],
    "inject_mode": "text",
}

# 诱饵副本（decoy copy）配置：方案 C 结果级令牌预埋
DECOY_COPY_CONFIG = {
    "root": DATA_DIR / "decoy_copies",
    "inject_mode": "text",          # text / json_field / table_row
    "token_prefix": "DPT",
    "max_injections_per_session": 5,
}

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

# 安全运行模式
# single_user: 单人办公助手模式（默认），未登记 agent 使用 owner 全权限兜底
# enterprise : 企业多角色模式，未登记 agent 返回空权限，全部工具默认拦截
SECURITY_MODES = ("single_user", "enterprise")
_security_mode = os.getenv("GOVAGENT_SECURITY_MODE", "single_user")
if _security_mode not in SECURITY_MODES:
    _security_mode = "single_user"
SECURITY_MODE = _security_mode

# 权限策略信号化开关
# True  = 权限层保持直接阻断/审批（默认，行为不变）
# False = 权限结果转为 R_permission 风险维度，由 DispositionEngine 统一决策
PERMISSION_FORCE_BLOCK = (
    os.getenv("GOVAGENT_PERMISSION_FORCE_BLOCK", "true").lower() == "true"
)

# 数据分级规则
# data_class 与风险分对应，按 CRITICAL > SENSITIVE > INTERNAL > PUBLIC 优先级命中
DATA_CLASS_RULES = {
    "CRITICAL": {
        "keywords": ["top secret", "绝密"],
        "path_markers": ["top_secret"],
        "risk_score": 0.9,
    },
    "SENSITIVE": {
        "keywords": [
            "customer", "citizen", "identity", "salary",
            "secret", "confidential", "客户", "公民", "身份证",
            "工资", "薪酬", "机密",
        ],
        "path_markers": ["secret", "confidential"],
        "risk_score": 0.7,
    },
    "INTERNAL": {
        "keywords": ["internal", "内部", "预算", "财务"],
        "path_markers": ["internal"],
        "risk_score": 0.4,
    },
    "PUBLIC": {
        "keywords": [],
        "path_markers": [],
        "risk_score": 0.0,
    },
}

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
