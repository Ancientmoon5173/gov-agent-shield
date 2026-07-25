"""
工具风险配置表。

定义每个工具的基础风险分和参数检测规则。
所有配置集中管理，方便调整和演示。
"""

# 工具基础风险配置
# key=工具名, value=基础风险分(0-1)
TOOL_RISK_CONFIG = {
    "search_knowledge_base": {
        "base_risk": 0.1,
        "risk_level": "LOW",
        "description": "知识库搜索（只读，风险极低）",
        "sensitive_params": [],
    },
    "generate_summary": {
        "base_risk": 0.1,
        "risk_level": "LOW",
        "description": "内容摘要生成（只读，风险极低）",
        "sensitive_params": [],
    },
    "read_document": {
        "base_risk": 0.3,
        "risk_level": "MEDIUM",
        "description": "读取政府文档（需要路径白名单）",
        "sensitive_params": ["file_path"],
    },
    "query_citizen_info": {
        "base_risk": 0.7,
        "risk_level": "HIGH",
        "description": "查询居民信息（涉及个人隐私）",
        "sensitive_params": ["name", "id_number"],
    },
    "upload_data": {
        "base_risk": 0.8,
        "risk_level": "VERY_HIGH",
        "description": "外部数据上传（高危，演示用）",
        "sensitive_params": ["data", "target"],
    },
}

# 参数敏感关键词（用于 ParameterRisk 计算）
PARAMETER_RISK_RULES = {
    "read_document": {
        "sensitive_keywords": [
            "secret", "password", "key",
            "密码", "合同", "机密", "密钥",
        ],
        "keyword_penalty": 0.3,
        "path_traversal_patterns": ["../", "..\\", "/etc/", "/var/", "C:\\Windows", "%2e%2e", "....//", "..%2f", "%2f%2e%2e%2f"],
        "traversal_penalty": 0.5,
    },
    "query_citizen_info": {
        "batch_keywords": ["全部", "所有", "all", "全量", "全部员工", "所有人", "所有用户"],
        "batch_penalty": 0.3,
        "full_id_pattern": r"[0-9]{18}",
        "full_id_penalty": 0.2,
    },
    "upload_data": {
        "external_target_patterns": ["http://", "https://", "ftp://", "smtp://", "smtps://"],
        "target_penalty": 0.2,
    },
}

def get_tool_base_risk(tool_name: str) -> float:
    """获取工具的基础风险分。"""
    config = TOOL_RISK_CONFIG.get(tool_name, {})
    return config.get("base_risk", 0.5)

def get_tool_risk_rules(tool_name: str) -> dict:
    """获取工具的参数风险规则。"""
    return PARAMETER_RISK_RULES.get(tool_name, {})
