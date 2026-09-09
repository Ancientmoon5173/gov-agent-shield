# -*- coding: utf-8 -*-
"""run_shield_eval.py — 固定 ToolCall 的 Shield 评测（真实 SecurityOrchestrator/check_tool_call，临时审计库）。
execution_observed=False（engine-level replay，不虚构执行）。"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from src.security import SecurityOrchestrator
from src.security.security_logger import SecurityLogger

AB = pathlib.Path(__file__).resolve().parent
cases = json.loads((AB/"attack_cases.json").read_text(encoding="utf-8"))
rows=[]
for c in cases:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ab_shield_"))
    logger = SecurityLogger(db_path=tmp/"d.db")
    orc = SecurityOrchestrator(security_logger=logger)
    session = f"AB-{c['case_id']}"
    if c.get("attack_prompt"):
        orc.check_input(session, c["attack_prompt"], "")
    for t in c["tool_calls"]:
        res = orc.check_tool_call(session, t["tool"], dict(t["params"]), agent_id="admin_agent")
        evs = logger.get_session_events(session)
        call_evs = sorted({e.get("event_type") for e in evs if e.get("call_id")==res.get("correlation",{}).get("call_id") and e.get("event_type")})
        rows.append({
            "case_id": c["case_id"], "tool_call_id": t["tool_call_id"], "tool": t["tool"],
            "params": t["params"],
            "data_class": res.get("data_class"), "behavior_risk": (res.get("behavior") or {}).get("behavior_score"),
            "permission_policy": res.get("permission_policy"),
            "risk_score": res.get("risk_score"), "risk_level": res.get("risk_level"),
            "disposition": res.get("action"), "blocked": bool(res.get("blocked")),
            "execution_status": res.get("execution_status"),
            "execution_observed": False,
            "execution_allowed": res.get("action") in ("allow","warn"),
            "audit_event_types": call_evs})
(AB/"shield_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("shield rows:", len(rows))
