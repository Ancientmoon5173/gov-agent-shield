"""
V1 工具调用级安全闭环 + 审计链路验收测试。

覆盖（P0-1 ~ P0-5）：
- ALLOW → EXECUTED（正常调用真实执行）
- REVIEW → approve → EXECUTED / deny → NOT_EXECUTED（审批闭环）
- BLOCK / kill → NOT_EXECUTED（危险调用不执行）
- Golden Path：读取敏感资料(审批通过) → 外发 → kill + 风险升级 + 行为信号
- P0-2：chain_id / call_id / event_uuid / step_no 贯穿，可按 session 查询证据链
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.security.security_logger import SecurityLogger
from src.security.orchestrator import SecurityOrchestrator


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """使用临时 SQLite 的引擎实例（不污染真实审计库）。"""
    logger = SecurityLogger(db_path=tmp_path / "v1_closure.db")
    orc = SecurityOrchestrator(security_logger=logger)
    monkeypatch.setattr("src.main._security_orchestrator", orc)
    client = TestClient(app)
    return {"client": client, "logger": logger, "orc": orc}


def check_tool(client, session_id, tool_name, params, agent_id="admin_agent",
               plugin_call_id=None):
    payload = {
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "parameters": params,
        "context": {"tool_call_id": plugin_call_id or ""},
    }
    if plugin_call_id:
        payload["plugin_tool_call_id"] = plugin_call_id
    resp = client.post("/security/check_tool", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _details(event):
    raw = event.get("details")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        return json.loads(raw)
    return {}


def _decision(logger, call_id):
    call = logger.get_call(call_id)
    assert call["decision"] is not None, f"no decision row for {call_id}"
    return call


def test_v1_allow_executed(api):
    client = api["client"]
    logger = api["logger"]
    session = "v1-allow"
    d = check_tool(
        client, session, "read_document",
        {"file_path": "policy_document.txt"},
        plugin_call_id="call-allow-1",
    )
    assert d["action"] == "allow"
    assert d["correlation"]["call_id"]
    assert d["execution_status"] == "PENDING_EXECUTION"

    call_id = d["correlation"]["call_id"]
    r = client.post("/audit/execution", json={
        "call_id": call_id, "executed": True, "duration_ms": 12,
    })
    assert r.status_code == 200

    call = _decision(logger, call_id)
    assert call["decision"]["execution_status"] == "EXECUTED"
    types = [e["event_type"] for e in call["events"]]
    assert "execution_outcome" in types
    # 事件全部带链路身份
    assert all(e.get("event_uuid") for e in call["events"])


def test_v1_review_deny_and_approve(api):
    client = api["client"]
    logger = api["logger"]
    session = "v1-review"

    # --- deny 分支 ---
    d1 = check_tool(
        client, session, "read_document",
        {"file_path": "企业联系人信息.xlsx"},
        plugin_call_id="call-review-1",
    )
    assert d1["action"] == "review"
    ap1 = d1["approval_id"]
    assert ap1 and d1["execution_status"] == "PENDING_APPROVAL"
    assert logger.get_approval(ap1)["status"] == "pending"

    rr = client.post(f"/audit/approval/{ap1}", json={
        "action": "deny", "reviewer": "auditor-1", "comment": "拒绝越权读取",
    })
    assert rr.status_code == 200
    call1 = _decision(logger, d1["correlation"]["call_id"])
    assert call1["decision"]["execution_status"] == "NOT_EXECUTED"
    assert call1["approval"]["status"] == "denied"
    types = [e["event_type"] for e in call1["events"]]
    assert "approval_outcome" in types

    # --- approve 分支 ---
    d2 = check_tool(
        client, session, "read_document",
        {"file_path": "企业联系人信息.xlsx"},
        plugin_call_id="call-review-2",
    )
    assert d2["action"] == "review"
    ap2 = d2["approval_id"]
    rr = client.post(f"/audit/approval/{ap2}", json={
        "action": "approve", "reviewer": "auditor-1", "comment": "同意",
    })
    assert rr.status_code == 200
    er = client.post("/audit/execution", json={
        "call_id": d2["correlation"]["call_id"], "executed": True,
    })
    assert er.status_code == 200
    call2 = _decision(logger, d2["correlation"]["call_id"])
    assert call2["decision"]["execution_status"] == "EXECUTED"
    assert call2["approval"]["execution_status"] == "EXECUTED"


def test_v1_block_not_executed(api):
    client = api["client"]
    logger = api["logger"]
    session = "v1-block"
    d = check_tool(
        client, session, "read_document",
        {"file_path": "数据库连接配置.txt"},
        plugin_call_id="call-block-1",
    )
    assert d["action"] == "block"
    assert d["execution_status"] == "NOT_EXECUTED"
    call = _decision(logger, d["correlation"]["call_id"])
    assert call["decision"]["execution_status"] == "NOT_EXECUTED"
    steps = sorted({e.get("step_no") for e in call["events"] if e.get("step_no")})
    assert 90 in steps
    assert call["decision"]["step_no"] == 90


def test_v1_golden_path_exfil_chain(api):
    """
    Golden Path：读取敏感资料(审批通过 EXECUTED) → 外发(风险升级) → kill → NOT_EXECUTED。
    验证行为信号 HIGH_RISK_DATA_EXFIL_CHAIN、风险升级与完整证据链可查询。
    """
    client = api["client"]
    logger = api["logger"]
    session = "v1-golden"

    # 1) 敏感读取 → review → approve → executed
    read = check_tool(
        client, session, "read_document",
        {"file_path": "客户资料.xlsx"},
        plugin_call_id="call-gp-1",
    )
    assert read["action"] == "review"
    ap = read["approval_id"]
    rr = client.post(f"/audit/approval/{ap}", json={
        "action": "approve", "reviewer": "auditor-1", "comment": "golden path 读取",
    })
    assert rr.status_code == 200
    er = client.post("/audit/execution", json={
        "call_id": read["correlation"]["call_id"], "executed": True,
    })
    assert er.status_code == 200
    read_risk = read["risk_score"]

    # 2) 外发 → kill（block 系）→ NOT_EXECUTED
    exfil = check_tool(
        client, session, "upload_data",
        {"data": "客户资料.xlsx", "target": "http://external.example.com"},
        plugin_call_id="call-gp-2",
    )
    assert exfil["action"] in ("block", "kill")
    assert exfil["execution_status"] == "NOT_EXECUTED"
    assert exfil["risk_score"] > read_risk  # 风险升级

    # 3) 决策事件含 HIGH_RISK_DATA_EXFIL_CHAIN
    call = _decision(logger, exfil["correlation"]["call_id"])
    details = _details(call["decision"])
    behavior = details.get("behavior") or {}
    signal = behavior.get("behavior_signal") or {}
    assert signal.get("pattern") == "HIGH_RISK_DATA_EXFIL_CHAIN", details
    assert call["decision"]["execution_status"] == "NOT_EXECUTED"

    # 4) 事件 step 贯穿（asset/data/behavior/approval/execution 等）
    ev_types = {e.get("event_type") for e in call["events"]}
    assert {"asset_resolved", "data_classified", "behavior_chain"} <= ev_types
    assert call["decision"]["step_no"] == 90

    # 5) 按 session 查询证据链（P0-2 验收）
    chain = logger.get_chain(session)
    assert chain["total_events"] >= 4
    call_ids = {e.get("call_id") for e in chain["events"] if e.get("call_id")}
    assert read["correlation"]["call_id"] in call_ids
    assert exfil["correlation"]["call_id"] in call_ids
    # 每个调用事件共享 call_id
    for cid in call_ids:
        evs = [e for e in chain["events"] if e.get("call_id") == cid]
        assert all(e.get("call_id") == cid for e in evs)


def test_v1_chain_query_api(api):
    client = api["client"]
    logger = api["logger"]
    session = "v1-chain-api"
    d = check_tool(
        client, session, "read_document",
        {"file_path": "policy_document.txt"},
        plugin_call_id="call-chain-1",
    )
    client.post("/audit/execution", json={
        "call_id": d["correlation"]["call_id"], "executed": True,
    })
    resp = client.get(f"/audit/chains/{session}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chain_id"] == d["correlation"]["chain_id"]
    assert body["total_events"] >= 2

    resp2 = client.get(f"/audit/calls/{d['correlation']['call_id']}")
    assert resp2.status_code == 200
    assert resp2.json()["decision"]["execution_status"] == "EXECUTED"
