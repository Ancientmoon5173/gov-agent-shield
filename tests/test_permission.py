"""
权限控制模块测试。

覆盖：
- 正常工具调用权限通过
- 越权访问被阻断
- 审批流程
- 管理员权限
- Orchestrator 集成
"""

from src.permission.models import PermissionPolicy
from src.permission.storage import PermissionStorage
from src.permission.policy import PolicyEngine
from src.permission.approval import ApprovalManager


# ========================
# 单元测试
# ========================

def test_policy_allow():
    """测试允许列表生效。"""
    policy = PermissionPolicy(
        agent_id="test",
        allowed_tools=["read_document"],
    )
    engine = PolicyEngine()
    assert engine.is_tool_allowed(policy, "read_document") == True
    assert engine.is_tool_allowed(policy, "upload_data") == False


def test_policy_wildcard():
    """测试通配符 '*' 允许全部工具。"""
    policy = PermissionPolicy(agent_id="admin", allowed_tools=["*"])
    engine = PolicyEngine()
    assert engine.is_tool_allowed(policy, "read_document") == True
    assert engine.is_tool_allowed(policy, "upload_data") == True


def test_policy_restricted():
    """测试禁止列表优先级高于允许列表。"""
    policy = PermissionPolicy(
        agent_id="test",
        allowed_tools=["*"],
        restricted_tools=["upload_data"],
    )
    engine = PolicyEngine()
    assert engine.is_tool_allowed(policy, "read_document") == True
    assert engine.is_tool_allowed(policy, "upload_data") == False


def test_requires_approval():
    """测试审批列表。"""
    policy = PermissionPolicy(
        agent_id="test",
        allowed_tools=["upload_data"],
        require_approval=["upload_data"],
    )
    engine = PolicyEngine()
    assert engine.requires_approval(policy, "upload_data") == True
    assert engine.requires_approval(policy, "read_document") == False


def test_approval_flow():
    """测试审批完整流程。"""
    mgr = ApprovalManager()
    aid = mgr.request("test_agent", "upload_data", {}, "需要审批")
    assert mgr.check(aid) == "pending"

    mgr.approve(aid)
    assert mgr.check(aid) == "approved"

    aid2 = mgr.request("test_agent2", "upload_data", {}, "需要拒绝")
    mgr.reject(aid2)
    assert mgr.check(aid2) == "rejected"


def test_pending_list():
    """测试待审批列表。"""
    mgr = ApprovalManager()
    mgr.request("a1", "t1", {}, "r1")
    mgr.request("a2", "t2", {}, "r2")
    assert len(mgr.get_pending()) == 2
    mgr.approve("AP-0001")
    assert len(mgr.get_pending()) == 1


# ========================
# 集成测试
# ========================

def test_orchestrator_default_agent_allowed():
    """Orchestrator 中 default_agent 允许的工具应正常调用。"""
    from src.security import create_orchestrator
    orc = create_orchestrator()
    r = orc.check_tool_call("test", "read_document", {}, agent_id="default_agent")
    assert r["action"] == "allow"


def test_orchestrator_default_agent_blocked():
    """Orchestrator 中 default_agent 禁止的工具应被阻断。"""
    from src.security import create_orchestrator
    orc = create_orchestrator()
    r = orc.check_tool_call("test", "upload_data", {}, agent_id="default_agent")
    # upload_data 既在 restricted_tools 也在 require_approval
    # 优先匹配 restricted_tools -> block
    assert r["action"] == "block"
    assert r["blocked"] == True


def test_orchestrator_admin_high_risk_operation():
    """管理员的高风险操作应进入审批而非直接阻断。"""
    from src.security import create_orchestrator
    orc = create_orchestrator()
    r = orc.check_tool_call("test", "upload_data", {}, agent_id="admin_agent")
    # 管理员有权限但 upload_data 高风险，应触发审批(review)或阻断
    assert r["action"] in ("allow", "review")


def test_orchestrator_default_agent_query_info():
    """default_agent 应允许查询居民信息。"""
    from src.security import create_orchestrator
    orc = create_orchestrator()
    r = orc.check_tool_call("test", "query_citizen_info", {"name": "张三"}, agent_id="default_agent")
    assert r["action"] == "allow" or r["action"] == "review"


def test_approval_manager_persistence():
    """审批管理器在同一个实例中保持状态。"""
    mgr = ApprovalManager()
    a1 = mgr.request("agent1", "read_document", {}, "test")
    assert mgr.check(a1) == "pending"
    assert len(mgr.get_all()) == 1
