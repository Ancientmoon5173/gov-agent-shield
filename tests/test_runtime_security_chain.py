"""
Agent Runtime Security 风险链路测试。

覆盖：
1. DataClassifier 数据分类进入风险计算
2. PermissionChecker 兼容模式（FORCE_BLOCK=true）直接阻断
3. 数据分类不依赖权限，只作为风险上下文
"""

from src.security.orchestrator import SecurityOrchestrator, PERMISSION_FORCE_BLOCK
from src.security import create_orchestrator


def _normal_upload_params():
    # 无外部地址 pattern，不触发参数外传加分
    return {"data": "report.txt", "target": "internal"}


def _customer_upload_params():
    # 外部地址触发参数风险加分，与普通上传形成对比
    return {"data": "customer.xlsx", "target": "http://external"}


def test_data_classifier_enters_risk_chain(monkeypatch):
    """数据分类进入风险链路：SENSITIVE 数据风险高于普通数据。"""
    monkeypatch.setattr(
        "src.security.orchestrator.PERMISSION_FORCE_BLOCK", False,
    )
    orc = create_orchestrator()

    customer_result = orc.check_tool_call(
        "chain-test-1", "upload_data", _customer_upload_params(),
        agent_id="admin_agent",
    )
    normal_result = orc.check_tool_call(
        "chain-test-1", "upload_data", _normal_upload_params(),
        agent_id="admin_agent",
    )

    assert customer_result["data_class"] == "SENSITIVE"
    assert customer_result["risk_score"] > normal_result["risk_score"]
    assert customer_result["action"] != "allow"


def test_permission_force_block_compat(monkeypatch):
    """兼容模式：default_agent 上传被权限层直接阻断。"""
    monkeypatch.setattr(
        "src.security.orchestrator.PERMISSION_FORCE_BLOCK", True,
    )
    orc = create_orchestrator()

    result = orc.check_tool_call(
        "chain-test-2", "upload_data", _customer_upload_params(),
        agent_id="default_agent",
    )

    assert result["action"] == "block"
    assert result["blocked"] is True
    assert result["permission_policy"] is not None


def test_data_class_independent_of_permission(monkeypatch):
    """同一 customer.xlsx 在 admin/default 两个 Agent 下都识别为 SENSITIVE。"""
    monkeypatch.setattr(
        "src.security.orchestrator.PERMISSION_FORCE_BLOCK", False,
    )
    orc = create_orchestrator()

    admin_result = orc.check_tool_call(
        "chain-test-3a", "upload_data", {"data": "customer.xlsx"},
        agent_id="admin_agent",
    )
    default_result = orc.check_tool_call(
        "chain-test-3b", "upload_data", {"data": "customer.xlsx"},
        agent_id="default_agent",
    )

    assert admin_result["data_class"] == "SENSITIVE"
    assert default_result["data_class"] == "SENSITIVE"

    assert (
        admin_result["permission_policy"]["role"]
        != default_result["permission_policy"]["role"]
    )
