"""
Single-user Mode 权限模块测试。

覆盖：
1. 单用户模式下，未注册 agent 调用普通工具，权限检查返回 allow
2. 单用户模式下，allowed_tools=["*"] 可以匹配任意工具名称
3. 单用户模式下，Risk Engine 仍可独立阻断高风险工具调用
4. 企业模式下，未注册 agent 调用工具，权限检查返回 block
"""

from src.config import SECURITY_MODE
from src.permission.storage import PermissionStorage
from src.permission.policy import PolicyEngine
from src.permission.checker import PermissionChecker, create_permission_checker
from src.security import create_orchestrator


def test_single_user_unregistered_agent_allowed():
    """单用户模式：未注册 agent 调用普通工具，权限检查返回 allow。"""
    storage = PermissionStorage(security_mode="single_user")
    checker = PermissionChecker(storage=storage)

    result = checker.check("unregistered-agent-001", "read_document", {"file_path": "政策文件.txt"})

    assert result.allowed is True
    assert result.action == "allow"
    assert result.policy is not None
    assert result.policy.role == "owner"


def test_single_user_wildcard_matches_any_tool():
    """单用户模式：owner 兜底策略的 allowed_tools=["*"] 匹配任意工具。"""
    storage = PermissionStorage(security_mode="single_user")
    policy = storage.get_policy("unregistered-agent-002")
    engine = PolicyEngine()

    assert policy.allowed_tools == ["*"]
    assert engine.is_tool_allowed(policy, "read_document") is True
    assert engine.is_tool_allowed(policy, "query_citizen_info") is True
    assert engine.is_tool_allowed(policy, "upload_data") is True


def test_single_user_risk_engine_still_blocks():
    """单用户模式：权限放行后，Risk Engine 仍可独立阻断高风险调用。"""
    orc = create_orchestrator()
    # 使用全新会话，避免行为链历史污染
    session_id = "single-user-risk-test"
    orc.behavior_analyzer.reset_session(session_id)

    result = orc.check_tool_call(
        session_id,
        "upload_data",
        {"data": "员工工资表", "target": "http://external"},
        agent_id="unregistered-agent-003",
    )

    # 权限层（single_user）应放行，但风险引擎独立阻断
    assert result["action"] in ("block", "kill")
    assert result["blocked"] is True
    assert result["defense_stage"] != "permission_checker"
    assert result["risk_score"] >= 0.7


def test_enterprise_unregistered_agent_blocked():
    """企业模式：未注册 agent 调用工具，权限检查返回 block。"""
    checker = create_permission_checker(security_mode="enterprise")

    result = checker.check("unregistered-agent-004", "read_document", {"file_path": "政策文件.txt"})

    assert result.allowed is False
    assert result.action == "block"
    assert result.policy is not None
    assert result.policy.role == "unknown"


def test_single_user_is_default_mode():
    """全局默认安全模式为 single_user。"""
    assert SECURITY_MODE == "single_user"
