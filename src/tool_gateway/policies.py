"""
安全策略定义。

每一条策略定义：什么情况下某个工具调用是安全的/不安全的。
"""

import re
from enum import Enum
from typing import Dict, Any, Optional, List


class Action(Enum):
    """处置动作枚举。"""
    ALLOW = "allow"       # 放行
    REVIEW = "review"     # 需要人工审批
    BLOCK = "block"       # 阻断
    KILL = "kill"         # 熔断（停止整个任务）


class SecurityPolicy:
    """安全策略定义。"""

    def __init__(
        self,
        name: str,
        tool_pattern: str,
        description: str = "",
        risk_score: float = 0.5,
        action: Action = Action.REVIEW,
        param_rules: Optional[List[Dict]] = None,
    ):
        self.name = name
        self.tool_pattern = re.compile(tool_pattern, re.IGNORECASE)
        self.description = description
        self.risk_score = risk_score
        self.action = action
        self.param_rules = param_rules or []

    def matches(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """检查工具调用是否匹配此策略。"""
        return bool(self.tool_pattern.search(tool_name))

    def evaluate(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        评估一次匹配的策略调用。

        会根据参数的具体内容计算动态风险。
        """
        dynamic_score = self.risk_score

        # 检查参数规则
        for rule in self.param_rules:
            param_name = rule.get("param")
            pattern = rule.get("pattern")
            score_delta = rule.get("score_delta", 0.1)

            if param_name in params:
                param_value = str(params[param_name])
                if pattern and re.search(pattern, param_value, re.IGNORECASE):
                    dynamic_score += score_delta

        # 根据最终评分决定动作
        if dynamic_score >= 0.8:
            final_action = Action.BLOCK
        elif dynamic_score >= 0.5:
            final_action = self.action
        else:
            final_action = Action.ALLOW

        return {
            "allowed": final_action in [Action.ALLOW, Action.REVIEW],
            "action": final_action.value,
            "risk_score": min(dynamic_score, 1.0),
            "reason": self.description,
        }


# ========================
# 预定义策略
# ========================

# 文件读取策略
FILE_READ_POLICY = SecurityPolicy(
    name="file_read",
    tool_pattern=r"(read_file|file_read|load_file|open_file)",
    description="读取文件操作，需要检查路径是否在允许范围内",
    risk_score=0.3,
    action=Action.REVIEW,
    param_rules=[
        {
            "param": "file_path",
            "pattern": r"(\.\./|/etc|/var|/root|C:\\Windows|secret|key|password)",
            "score_delta": 0.4,
        },
    ],
)

# 命令执行策略
COMMAND_EXEC_POLICY = SecurityPolicy(
    name="command_execution",
    tool_pattern=r"(run_command|exec|shell|bash|cmd|powershell|terminal)",
    description="执行系统命令，高风险操作",
    risk_score=0.7,
    action=Action.REVIEW,
    param_rules=[
        {
            "param": "command",
            "pattern": r"(rm|del|format|dd|shutdown|reboot|curl|wget)",
            "score_delta": 0.2,
        },
    ],
)

# 网络访问策略
NETWORK_ACCESS_POLICY = SecurityPolicy(
    name="network_access",
    tool_pattern=r"(http|request|fetch|download|curl|wget|api_call)",
    description="访问外部网络资源",
    risk_score=0.4,
    action=Action.REVIEW,
)

# 数据库访问策略
DATABASE_ACCESS_POLICY = SecurityPolicy(
    name="database_access",
    tool_pattern=r"(query|db_query|sql|database|execute_sql)",
    description="数据库查询操作",
    risk_score=0.4,
    action=Action.REVIEW,
    param_rules=[
        {
            "param": "query",
            "pattern": r"(drop|delete|truncate|alter)",
            "score_delta": 0.4,
        },
    ],
)

# 默认策略集合
DEFAULT_POLICIES = [
    FILE_READ_POLICY,
    COMMAND_EXEC_POLICY,
    NETWORK_ACCESS_POLICY,
    DATABASE_ACCESS_POLICY,
]


def get_default_gateway():
    """创建一个配置好默认策略的网关。"""
    from .gateway import ToolGateway

    gateway = ToolGateway()
    for policy in DEFAULT_POLICIES:
        gateway.register_policy(policy)
    return gateway
