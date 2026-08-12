"""
Shadow Decoy 路由（方案 A）测试。

覆盖：
- dry-run 默认只审计不改写
- dry_run=False 时生成可执行重定向目标
- 冷却机制
- 写工具永不重定向
- 普通文件不重定向
- 重定向目标路径穿越防护
- SecurityOrchestrator 集成与 decoy_route_triggered 审计
"""

import json

from src.security import create_orchestrator
from src.security.decoy_manager import DecoyManager
from src.security.decoy_copy_generator import create_decoy_copy_generator


ASSET_CUSTOMER = {
    "matched": True,
    "asset_type": "customer_data",
    "sensitivity": "SENSITIVE",
    "owner": "business_department",
    "policy": "require_review",
}


def _route(manager, session_id="s1", risk=0.8, params=None, asset=None):
    return manager.build_route(
        session_id=session_id,
        tool_name="read_document",
        params=params or {"file_path": "customer_records.xlsx"},
        asset_context=asset or ASSET_CUSTOMER,
        risk_score=risk,
    )


def test_dry_run_default_audits_without_enabling():
    manager = DecoyManager()
    result = _route(manager)

    assert result["matched"] is True
    assert result["enabled"] is False
    assert result["dry_run"] is True
    assert result["policy_id"] == "decoy_route:customer_data"
    assert result["redirect_target"].startswith("/engine/decoy/customer/")
    assert result["original_target"] == "customer_records.xlsx"


def test_enabled_when_dry_run_disabled(tmp_path):
    manager = DecoyManager(
        copy_generator=create_decoy_copy_generator(
            config={"root": tmp_path}
        )
    )
    manager._route_config["dry_run"] = False

    result = _route(manager)

    assert result["matched"] is True
    assert result["enabled"] is True
    assert result["token"].startswith("DPT")
    assert result["redirect_target"] == str(
        tmp_path / "s1" / "customer_data" / "customer_records.xlsx"
    )
    assert (tmp_path / "s1" / "customer_data" / "customer_records.xlsx").exists()


def test_cooldown_skips_repeated_route():
    manager = DecoyManager()
    session_id = "session-cooldown"

    first = _route(manager, session_id=session_id)
    second = _route(manager, session_id=session_id)

    assert first["matched"] is True
    assert second["matched"] is False


def test_write_tool_never_redirected():
    manager = DecoyManager()
    result = manager.build_route(
        session_id="s-write",
        tool_name="upload_data",
        params={"data": "customer_records.xlsx", "target": "http://external"},
        asset_context=ASSET_CUSTOMER,
        risk_score=0.9,
    )

    assert result["matched"] is False
    assert result["enabled"] is False


def test_normal_file_not_redirected():
    manager = DecoyManager()
    result = manager.build_route(
        session_id="s-normal",
        tool_name="read_document",
        params={"file_path": "public_notice.md"},
        asset_context={"matched": False, "sensitivity": "LOW"},
        risk_score=0.9,
    )

    assert result["matched"] is False


def test_redirect_target_blocks_path_traversal():
    manager = DecoyManager()
    manager._route_mapping = {
        "engine_decoy_root": "/engine/decoy/",
        "mappings": [
            {
                "asset_type": "customer_data",
                "min_sensitivity": "SENSITIVE",
                "template": "../../escape/{filename}",
            }
        ],
    }

    result = _route(manager)

    assert result["matched"] is False
    assert result["redirect_target"] == ""


def test_orchestrator_dry_run_audit():
    orc = create_orchestrator()
    session_id = "route-orchestrator-dry"

    result = orc.check_tool_call(
        session_id,
        "read_document",
        {"file_path": "客户名单_机密.xlsx"},
        agent_id="admin_agent",
    )

    assert result["decoy_route"]["matched"] is True
    assert result["decoy_route"]["enabled"] is False
    assert result["decoy_route"]["policy_id"] == "decoy_route:customer_data"

    events = orc.security_logger.get_session_events(session_id)
    route_events = [
        e for e in events if e.get("event_type") == "decoy_route_triggered"
    ]
    assert route_events
    assert json.loads(route_events[0]["details"])["redirect_target"].startswith(
        "/engine/decoy/customer/"
    )


def test_orchestrator_enabled_route(tmp_path):
    orc = create_orchestrator()
    orc.decoy_manager._route_config["dry_run"] = False
    orc.decoy_manager.copy_generator._root = tmp_path
    session_id = "route-orchestrator-enabled"

    result = orc.check_tool_call(
        session_id,
        "read_document",
        {"file_path": "客户名单_机密.xlsx"},
        agent_id="admin_agent",
    )

    assert result["decoy_route"]["matched"] is True
    assert result["decoy_route"]["enabled"] is True
    assert result["decoy_route"]["token"].startswith("DPT")
    assert result["decoy_route"]["redirect_target"].startswith(
        str(tmp_path)
    )
    copy_file = (
        tmp_path / session_id / "customer_data" / "客户名单_机密.xlsx"
    )
    assert copy_file.exists()

    events = orc.security_logger.get_session_events(session_id)
    injected = [
        e for e in events if e.get("event_type") == "data_provenance_injected"
    ]
    assert injected
