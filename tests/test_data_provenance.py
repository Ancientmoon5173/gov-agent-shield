"""
数据溯源令牌（方案 C 第一阶段）测试。

覆盖：
- 外发参数命中令牌 → 泄漏信号
- 未携带令牌 → 不误报
- 过期令牌被忽略
- 非外发/写入类工具不扫描
- SecurityOrchestrator 命中令牌 → block + 审计
"""

from src.security import create_orchestrator
from src.security.data_provenance import DataProvenanceTracker
from src.security.orchestrator import SecurityOrchestrator


def test_scan_leak_hit_in_external_tool():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-1", "call-1", "DPT-demo-001", {"source": "mail"})

    result = tracker.scan_leak(
        "send_email",
        {"to": "external@example.com", "body": "内容含 DPT-demo-001"},
    )

    assert result["hit"] is True
    assert result["token"] == "DPT-demo-001"
    assert result["token_info"]["session_id"] == "sess-dpt-1"


def test_scan_leak_no_token_no_hit():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-2", "call-2", "DPT-demo-002")

    result = tracker.scan_leak(
        "upload_data",
        {"data": "customer_records.xlsx", "target": "http://external"},
    )

    assert result["hit"] is False


def test_expired_token_ignored():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-3", "call-3", "DPT-demo-003")
    tracker._tokens["DPT-demo-003"]["expires_at"] = 0

    result = tracker.scan_leak(
        "send_email",
        {"body": "DPT-demo-003"},
    )

    assert result["hit"] is False


def test_non_target_tool_not_scanned():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-4", "call-4", "DPT-demo-004")

    result = tracker.scan_leak(
        "read_document",
        {"file_path": "DPT-demo-004.md"},
    )

    assert result["hit"] is False


def test_orchestrator_blocks_leak_and_audits():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-orc", "call-1", "DPT-orc-001")
    orc = SecurityOrchestrator(data_provenance_tracker=tracker)

    result = orc.check_tool_call(
        "sess-dpt-orc",
        "upload_data",
        {
            "data": "customer_records.xlsx",
            "target": "http://external",
            "body": "附件内容 DPT-orc-001",
        },
        agent_id="admin_agent",
    )

    assert result["action"] == "block"
    assert result["blocked"] is True
    assert result["policy_id"] == "data_provenance:leak"
    assert result["data_provenance"]["hit"] is True

    events = orc.security_logger.get_session_events("sess-dpt-orc")
    leak_events = [
        e for e in events
        if e.get("event_type") == "data_provenance_leak_detected"
    ]
    assert leak_events
    assert leak_events[0]["policy_id"] == "data_provenance:leak"


def test_orchestrator_normal_call_no_leak_signal():
    tracker = DataProvenanceTracker()
    tracker.register("sess-dpt-ok", "call-1", "DPT-ok-001")
    orc = SecurityOrchestrator(data_provenance_tracker=tracker)

    result = orc.check_tool_call(
        "sess-dpt-ok",
        "read_document",
        {"file_path": "public_notice.md"},
        agent_id="admin_agent",
    )

    assert result["data_provenance"]["hit"] is False
