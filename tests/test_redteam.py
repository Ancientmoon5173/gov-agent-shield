"""Red Team 攻击测试。
对 attack_samples.json 中的所有样本运行完整安全检测链路。
"""
import json, pathlib, datetime
PATH = pathlib.Path("samples/red_team/all_attack_samples.json")
from src.security import create_orchestrator
from src.agent.planner import create_planner

SAMPLES = json.loads(PATH.read_text(encoding="utf-8"))

def is_at_risk(level):
    return level in ("HIGH", "CRITICAL", "VERY_HIGH")


def run_redteam(limit=None):
    orc = create_orchestrator()
    planner = create_planner()
    results = []
    missed = []
    detailed_traces = []
    batch = SAMPLES[:limit] if limit else SAMPLES
    for s in batch:
        sid = s["id"]
        prompt = s["prompt"]
        expected_level = s["level"]

        # 1. Input detection
        ic = orc.check_input(sid, prompt)
        input_blocked = ic["action"] in ("block", "kill")

        # 2. Planner tool matching
        tc = planner.plan(prompt)
        tool_found = tc.is_valid()

        # 3. Tool call detection (if tool was found)
        tool_blocked = False
        sec_info = {}
        if tool_found:
            sec_result = orc.check_tool_call(sid, tc.tool_name, tc.parameters, prompt)
            tool_blocked = sec_result["blocked"] or sec_result["action"] in ("block", "kill")
            sec_info = {"action": sec_result["action"], "level": sec_result["risk_level"], "score": sec_result["risk_score"]}

        system_blocked = input_blocked or tool_blocked
        # (Omitted)
        results.append({
            "id": sid, "category": s["category"], "level": expected_level,
            "input_action": ic["action"], "tool_name": tc.tool_name if tool_found else "no_tool",
            "tool_blocked": tool_blocked, "system_blocked": system_blocked,
            "at_risk": is_at_risk(expected_level),
        })

        # Build detailed trace for this sample
        trace = {
            "id": sid, "category": s["category"],
            "prompt": prompt[:200], "expected_level": expected_level,
            "planner": {
                "tool_name": tc.tool_name if tool_found else "",
                "parameters": dict(tc.parameters) if tool_found else {},
                "reasoning": tc.reasoning if tool_found else "\u65e0\u5339\u914d\u5de5\u5177",
            },
            "security_chain": [
                {"stage": "input_guard", "result": ic["action"], "risk_score": ic.get("risk_score",0), "risk_level": ic.get("risk_level",""), "findings": len(ic.get("findings",[]))},
                {"stage": "planner", "result": "matched" if tool_found else "no_match", "tool_name": tc.tool_name if tool_found else ""},
            ],
            "final_decision": {"blocked": system_blocked, "action": "", "risk_level": "", "risk_score": 0, "reason": ""},
        }
        if tool_found:
            trace["security_chain"].append({"stage": "parameter_checker", "result": "flagged" if sec_result.get("param_findings") else "passed", "findings_count": len(sec_result.get("param_findings",[]))})
            trace["security_chain"].append({"stage": "behavior_analyzer", "result": "flagged" if sec_result.get("behavior",{}).get("behavior_score",0) > 0 else "passed", "score": sec_result.get("behavior",{}).get("behavior_score",0)})
            if sec_result.get("decoy",{}).get("triggered"):
                trace["security_chain"].append({"stage": "decoy_manager", "result": "triggered", "detail": sec_result["decoy"].get("detail","")})
            trace["security_chain"].append({"stage": "risk_engine", "result": sec_result["action"], "risk_score": sec_result.get("risk_score",0), "risk_level": sec_result.get("risk_level",""), "defense_stage": sec_result.get("defense_stage",""), "decision_reason": sec_result.get("decision_reason","")})
            trace["final_decision"] = {"blocked": system_blocked, "action": sec_result["action"], "risk_level": sec_result.get("risk_level",""), "risk_score": sec_result.get("risk_score",0), "reason": sec_result.get("decision_reason", sec_result.get("reason",""))}
        else:
            trace["final_decision"] = {"blocked": system_blocked, "action": ic["action"], "risk_level": ic.get("risk_level","LOW"), "risk_score": ic.get("risk_score",0), "reason": ic.get("reason","\u65e0\u5de5\u5177\u5339\u914d")}
        detailed_traces.append(trace)
    return results, missed, detailed_traces


def summarize(results, missed=None):
    total = len(results)
    at_risk_total = sum(1 for r in results if r["at_risk"])
    blocked = sum(1 for r in results if r["system_blocked"])
    by_cat = {}
    for r in results:
        c = r["category"]
        if c not in by_cat:
            by_cat[c] = {"total": 0, "at_risk": 0, "blocked": 0}
        by_cat[c]["total"] += 1
        if r["at_risk"]:
            by_cat[c]["at_risk"] += 1
        if r["system_blocked"]:
            by_cat[c]["blocked"] += 1

    pre_blocked = sum(1 for r in results if r.get("pre_blocked"))
    tool_blocked = sum(1 for r in results if r.get("tool_blocked") and not r.get("pre_blocked"))
    blocked = pre_blocked + tool_blocked
    
    print(f"\n========= Red Team 测试报告 =========")
    print(f"总样本: {total}")
    print(f"高风险样本: {at_risk_total}")
    print(f"系统拦截: {blocked} (pre_block={pre_blocked}, tool_chain={tool_blocked})")
    print(f"攻击成功率(ASR): {(at_risk_total - blocked)/at_risk_total*100:.1f}%" if at_risk_total else "N/A")
    print(f"防御率: {blocked/at_risk_total*100:.1f}%" if at_risk_total else "N/A")
    print(f"\n按类别:")
    for cat, info in sorted(by_cat.items()):
        rate = info["blocked"]/info["at_risk"]*100 if info["at_risk"] else 0
        print(f"  {cat:30s} total={info['total']:3d} at_risk={info['at_risk']:3d} blocked={info['blocked']:3d} ({rate:.0f}%)")
    if missed:
        print(f"\n未拦截样本 ({len(missed)}):")
        for m in missed[:10]:
            print(f"  [{m['category']}] {m['id']}: {m['prompt']}")
        if len(missed) > 10:
            print(f"  ... 还有 {len(missed)-10} 个")
    # Export debug reports
    debug_dir = pathlib.Path("debug_reports")
    debug_dir.mkdir(parents=True, exist_ok=True)
    report = {"total": total, "at_risk": at_risk_total, "blocked": blocked, "pre_blocked": pre_blocked, "tool_blocked": tool_blocked, "missed_count": len(missed) if missed else 0, "missed": missed[:20] if missed else []}
    (debug_dir / "redteam_latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "missed_samples.json").write_text(json.dumps(missed if missed else [], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"total": total, "at_risk": at_risk_total, "blocked": blocked, "pre_blocked": pre_blocked, "tool_blocked": tool_blocked, "missed": missed}


def test_redteam_baseline():
    """Red Team baseline test."""
    results, missed, traces = run_redteam()
    stats = summarize(results, missed)
    assert stats["blocked"] > 0, "Should block at least some attacks"
    with open("redteam_missed.json", "w") as f:
        json.dump(missed, f, ensure_ascii=False, indent=2)
    # Save timestamped trace file
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_dir = pathlib.Path("debug_reports/redteam_history")
    hist_dir.mkdir(parents=True, exist_ok=True)
    trace_file = hist_dir / f"redteam_trace_{ts}.json"
    trace_file.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    (pathlib.Path("debug_reports/redteam_latest.json")).write_text(json.dumps(traces[:5], ensure_ascii=False, indent=2), encoding="utf-8") if False else None
