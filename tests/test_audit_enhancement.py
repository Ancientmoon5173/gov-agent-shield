"""
审计溯源增强测试。

覆盖：
- block 事件可查询 event_type / risk_score / decision_reason / policy_id
- 旧数据库 ALTER TABLE 兼容升级
- 行为链事件的 chain_summary 记录
"""

import sqlite3

from src.security import create_orchestrator
from src.security.security_logger import SecurityLogger


def test_block_event_audit_fields(monkeypatch):
    """权限 block 事件应记录完整审计字段。"""
    monkeypatch.setattr("src.security.orchestrator.PERMISSION_FORCE_BLOCK", True)
    orc = create_orchestrator()
    session_id = "audit-block-test"

    result = orc.check_tool_call(
        session_id,
        "upload_data",
        {"data": "customer.xlsx", "target": "http://external"},
        agent_id="default_agent",
    )

    assert result["action"] == "block"
    events = orc.security_logger.get_session_events(session_id)
    perm_events = [e for e in events if e["check_type"] == "permission"]
    assert perm_events

    event = perm_events[-1]
    assert event["event_type"] == "permission_violation"
    assert event["risk_score"] == 1.0
    assert event["policy_id"] == "permission:block"
    assert event["decision_reason"]


def test_legacy_db_compat(tmp_path):
    """旧库缺少新列时，应通过 ALTER TABLE 兼容升级。"""
    db_path = tmp_path / "legacy_security_events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT,
            check_type TEXT NOT NULL,
            input_text TEXT,
            tool_name TEXT,
            tool_params TEXT,
            risk_score REAL,
            risk_level TEXT,
            disposition TEXT,
            details TEXT
        )"""
    )
    conn.commit()
    conn.close()

    logger = SecurityLogger(db_path=db_path)
    logger.log_check(
        "legacy-session",
        "tool_call",
        tool_name="read_document",
        risk_score=0.5,
        disposition="review",
        event_type="tool_risk",
        policy_id="disposition:review",
        decision_reason="可疑行为，需要确认",
        defense_stage="risk_engine",
        chain_summary="read_document",
    )

    events = logger.get_session_events("legacy-session")
    assert len(events) == 1
    assert events[0]["event_type"] == "tool_risk"
    assert events[0]["policy_id"] == "disposition:review"
    assert events[0]["decision_reason"]


def test_behavior_chain_event(monkeypatch):
    """行为链事件应记录 event_type 与 chain_summary。"""
    monkeypatch.setattr("src.security.orchestrator.PERMISSION_FORCE_BLOCK", False)
    orc = create_orchestrator()
    session_id = "audit-chain-test"
    orc.start_session(session_id)

    orc.check_tool_call(
        session_id,
        "read_document",
        {"file_path": "customer.xlsx"},
        agent_id="admin_agent",
    )
    orc.check_tool_call(
        session_id,
        "upload_data",
        {"data": "customer.xlsx", "target": "http://external"},
        agent_id="admin_agent",
    )

    events = orc.security_logger.get_session_events(session_id)
    tool_events = [e for e in events if e["check_type"] == "tool_call"]
    assert tool_events

    last = tool_events[-1]
    assert last["event_type"] == "behavior_chain"
    assert last["chain_summary"] == "read_document -> upload_data"
