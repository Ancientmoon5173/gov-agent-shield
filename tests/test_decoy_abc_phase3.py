"""
Phase 3：Decoy ABC 闭环测试。

覆盖：
- Shadow Decoy Route 支持真实 read 工具与 path 参数
- 路由审计保留 original_params / modified_params
- Behavior Decoy 对个人资产产生低权重虚拟命中
- Data Provenance Token 支持撤销
- C-2a 诱饵副本令牌被外发工具命中时阻断
- C-2b 对真实 read 的高敏资产返回结果注入指令
"""

import json

from src.security import create_orchestrator
from src.security.data_provenance import DataProvenanceTracker
from src.security.decoy_copy_generator import create_decoy_copy_generator
from src.security.decoy_manager import DecoyManager
from src.security.orchestrator import SecurityOrchestrator


ASSET_CONTACT = {
    "matched": True,
    "asset_id": "asset-contact-001",
    "asset_type": "personal_information",
    "sensitivity": "HIGH",
    "owner": "数据管理科",
    "sharing_policy": "REVIEW_REQUIRED",
    "risk_score": 0.6,
}


def _route_manager(tmp_path):
    manager = DecoyManager(
        copy_generator=create_decoy_copy_generator(config={"root": tmp_path})
    )
    manager._route_config["dry_run"] = False
    return manager


def test_shadow_route_supports_real_read_tool(tmp_path):
    manager = _route_manager(tmp_path)
    result = manager.build_route(
        session_id="s1",
        tool_name="read",
        params={"path": "企业联系人信息.xlsx"},
        asset_context=ASSET_CONTACT,
        risk_score=0.8,
    )

    assert result["matched"] is True
    assert result["enabled"] is True
    assert result["target_param"] == "path"
    assert result["token"].startswith("DPT")
    assert result["redirect_target"].startswith(str(tmp_path))
    assert (
        tmp_path / "s1" / "personal_information" / "企业联系人信息.xlsx"
    ).exists()


def test_route_audit_contains_original_and_modified_params(tmp_path):
    manager = _route_manager(tmp_path)
    result = manager.build_route(
        session_id="s2",
        tool_name="read",
        params={"path": "企业联系人信息.xlsx"},
        asset_context=ASSET_CONTACT,
        risk_score=0.8,
    )

    assert result["original_params"] == {"path": "企业联系人信息.xlsx"}
    assert result["modified_params"] == {
        "path": result["redirect_target"],
    }


def test_decoy_b_virtual_hit_for_personal_asset():
    orc = create_orchestrator()
    session_id = "phase3-b"
    result = orc.check_tool_call(
        session_id,
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )

    events = orc.security_logger.get_session_events(session_id)
    hits = [
        e for e in events if e.get("event_type") == "decoy_virtual_hit"
    ]
    assert hits
    details = json.loads(hits[-1]["details"])
    assert details["risk_increment"] <= 0.05
    assert result["asset"]["matched"] is True


def test_revoked_token_not_scanned():
    tracker = DataProvenanceTracker()
    tracker.register("s-revoke", "call-1", "DPT-revoked-001")
    tracker.revoke("DPT-revoked-001")

    result = tracker.scan_leak(
        "upload_file",
        {"file": "out.xlsx", "body": "内容含 DPT-revoked-001"},
    )

    assert result["hit"] is False


def test_c2a_copy_token_blocks_upload(tmp_path):
    tracker = DataProvenanceTracker()
    generator = create_decoy_copy_generator(
        tracker=tracker,
        config={"root": tmp_path},
    )
    copy = generator.create_copy(
        session_id="s-c2a",
        asset_type="credential",
        filename="数据库连接配置.txt",
    )
    orc = SecurityOrchestrator(data_provenance_tracker=tracker)

    result = orc.check_tool_call(
        "s-c2a",
        "upload_file",
        {
            "file": "out.txt",
            "target": "http://external.example.com",
            "body": f"附件内容 {copy['token']}",
        },
        agent_id="admin_agent",
    )

    assert result["action"] == "block"
    assert result["policy_id"] == "data_provenance:leak"
    assert result["data_provenance"]["hit"] is True


def test_real_read_high_asset_returns_inject_token():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "phase3-c2b",
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )

    assert result["inject_token"] is not None
    assert result["inject_token"]["token"].startswith("DPT")
    assert result["inject_token"]["target_param"] == "path"
