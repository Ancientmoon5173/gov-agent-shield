"""Red Team 攻击测试。
对 attack_samples.json 中的所有样本运行完整安全检测链路。
"""
import json, pathlib
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
    batch = SAMPLES[:limit] if limit else SAMPLES
    for s in batch:
        sid = s["id"]
        prompt = s["prompt"]
        expected_level = s["level"]

        # 1. Input detection
        ic = orc.check_input(sid, prompt)
        input_blocked = ic["action"] in ("block", "kill", "review")

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

        system_blocked = input_blocked or tool_blocked or ic["action"] == "review"
        results.append({
            "id": sid, "category": s["category"], "level": expected_level,
            "input_action": ic["action"], "tool_name": tc.tool_name if tool_found else "no_tool",
            "tool_blocked": tool_blocked, "system_blocked": system_blocked,
            "at_risk": is_at_risk(expected_level),
        })
    return results, []


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
    return {"total": total, "at_risk": at_risk_total, "blocked": blocked, "pre_blocked": pre_blocked, "tool_blocked": tool_blocked, "missed": missed}


def test_redteam_baseline():
    """Red Team baseline test."""
    results, missed = run_redteam()
    stats = summarize(results, missed)
    assert stats["blocked"] > 0, "Should block at least some attacks"
    with open("redteam_missed.json", "w") as f:
        import json
        json.dump(missed, f, ensure_ascii=False, indent=2)
