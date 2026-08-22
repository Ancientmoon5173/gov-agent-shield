"""
Phase 3.5：Decoy ABC 稳定性验证。

目标：
- 合法政务业务流程不能被 Decoy 阻断
- 普通文件不触发 Decoy ABC
- Shadow Route 仅对 credential / personal_information 高风险读取进入 redirect
"""

from src.security import create_orchestrator
from src.security.decoy_copy_generator import create_decoy_copy_generator
from src.security.decoy_manager import DecoyManager


def test_legal_workflow_not_blocked():
    orc = create_orchestrator()
    session_id = "stability-legal"

    read_result = orc.check_tool_call(
        session_id,
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )
    generate_result = orc.check_tool_call(
        session_id,
        "generate_report",
        {"content": "2026年Q2园区企业服务报告"},
        agent_id="admin_agent",
    )
    upload_result = orc.check_tool_call(
        session_id,
        "upload_file",
        {"file": "园区企业服务报告.pdf", "target": "市数字化发展中心"},
        agent_id="admin_agent",
    )

    assert read_result["action"] not in ("block", "kill")
    assert read_result["risk_score"] >= 0.5
    assert generate_result["action"] == "allow"
    assert upload_result["action"] not in ("block", "kill")

    assert read_result["decoy_route"]["matched"] is False
    assert upload_result["decoy_route"]["matched"] is False
    assert upload_result["data_provenance"]["hit"] is False


def test_ordinary_files_do_not_trigger_decoy_abc():
    orc = create_orchestrator()
    steps = [
        ("read", {"path": "policy.pdf"}),
        ("upload_file", {"file": "policy.pdf", "target": "市数字化发展中心"}),
        ("read", {"path": "meeting.docx"}),
        ("upload_file", {"file": "meeting.docx", "target": "市数字化发展中心"}),
    ]

    for index, (tool_name, params) in enumerate(steps):
        result = orc.check_tool_call(
            f"stability-ordinary-{index}",
            tool_name,
            params,
            agent_id="admin_agent",
        )
        assert result["action"] not in ("block", "kill")
        assert result["asset"]["matched"] is False
        assert result["decoy_route"]["matched"] is False
        assert result["data_provenance"]["hit"] is False
        assert result["behavior"]["behavior_signal"]["pattern"] == "none"


def test_shadow_route_only_credential_and_personal_information(tmp_path):
    manager = DecoyManager(
        copy_generator=create_decoy_copy_generator(config={"root": tmp_path})
    )
    manager._route_config["dry_run"] = False

    cases = [
        (
            "credential",
            {
                "matched": True,
                "asset_type": "credential",
                "sensitivity": "CRITICAL",
            },
            True,
        ),
        (
            "personal_information",
            {
                "matched": True,
                "asset_type": "personal_information",
                "sensitivity": "HIGH",
            },
            True,
        ),
        (
            "financial_document",
            {
                "matched": True,
                "asset_type": "financial_document",
                "sensitivity": "HIGH",
            },
            False,
        ),
        (
            "customer_data",
            {
                "matched": True,
                "asset_type": "customer_data",
                "sensitivity": "SENSITIVE",
            },
            False,
        ),
        (
            "ordinary",
            {
                "matched": False,
                "asset_type": "",
                "sensitivity": "LOW",
            },
            False,
        ),
    ]

    for index, (label, asset, expected) in enumerate(cases):
        result = manager.build_route(
            session_id=f"stability-route-{index}",
            tool_name="read",
            params={"path": f"{label}.txt"},
            asset_context=asset,
            risk_score=0.9,
        )
        assert result["matched"] is expected, label
