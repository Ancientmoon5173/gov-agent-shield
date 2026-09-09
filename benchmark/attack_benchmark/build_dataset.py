# -*- coding: utf-8 -*-
"""build_dataset.py — 由 v1.0 engine ground-truth 构建固定 ToolCall 攻击基准（只读 src 规则常量，不改 src）。"""
import json, pathlib, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from src.config import DATA_CLASS_RULES

ROOT = pathlib.Path(__file__).resolve().parents[2]
AB = pathlib.Path(__file__).resolve().parent

src_fx = ROOT / "benchmark" / "fixtures"
dst_fx = AB / "fixtures"
if not dst_fx.exists():
    shutil.copytree(src_fx, dst_fx)

def classify(text):
    low = text.lower()
    for lv in ("CRITICAL", "SENSITIVE", "INTERNAL"):
        cfg = DATA_CLASS_RULES[lv]
        if any(k.lower() in low for k in cfg.get("keywords", [])) or \
           any(m.lower() in low for m in cfg.get("path_markers", [])):
            return lv
    return "PUBLIC"

cases = json.loads((ROOT/"benchmark/datasets/v1.0_benchmark/cases/cases.json").read_text(encoding="utf-8"))
EXFIL = {"upload_data","upload_file","send_email","http_request"}
EXT_MARK = ["http://","https://","@","collect.example","example.com","ftp://"]

attack_cases=[]; expected_map={}
for c in cases:
    cid=c["case_id"]; var=c["variant"]["type"]; sid=c["scenario_id"]
    tool_calls=[{"tool": st["tool_name"], "params": st.get("params", {}), "tool_call_id": f"{cid}-S{i}"}
                for i, st in enumerate(c.get("reference_plan", []), start=1)]
    files=[p.replace("benchmark/fixtures/","",1) for p in c.get("fixtures",{}).get("files",[])]
    params_txt = json.dumps(c.get("reference_plan", []), ensure_ascii=False) + " " + " ".join(files)
    data_class = classify(params_txt)
    is_attack = var in ("P","E","C","A")
    ext = var=="E" or any(t["tool"] in EXFIL and any(m in json.dumps(t["params"],ensure_ascii=False).lower() for m in EXT_MARK) for t in tool_calls)
    attack_cases.append({"case_id": cid, "scenario_id": sid, "variant": var,
        "description": f"{c['scenario']} ({var})",
        "attack_prompt": (c.get("input") or {}).get("user_input","") if var=="A" else "",
        "tool_calls": tool_calls, "fixture_refs": files,
        "ground_truth": {"is_attack": is_attack,
                         "requires_sensitive_asset": data_class in ("SENSITIVE","CRITICAL"),
                         "requires_external_transfer": ext,
                         "expected_attack_trigger": is_attack}})
    expected_map[cid] = {"case_id": cid, "expected_data_class": data_class,
        "expected_behavior_risk": str(c["expected"].get("risk_level","LOW")),
        "expected_disposition": str(c["expected"].get("action","allow")).upper(),
        "expected_execution": c["expected"].get("action") in ("allow","warn")}

(AB/"attack_cases.json").write_text(json.dumps(attack_cases, ensure_ascii=False, indent=1), encoding="utf-8")
(AB/"expected_results.json").write_text(json.dumps({"cases": expected_map}, ensure_ascii=False, indent=1), encoding="utf-8")
base=[{"case_id": c["case_id"], "tool_call_id": t["tool_call_id"], "tool": t["tool"],
       "params": t["params"], "result_type": "BASELINE_REPLAY", "execution_observed": False,
       "expected_behavior": "ALLOW_OR_EXECUTE"} for c in attack_cases for t in c["tool_calls"]]
(AB/"baseline_results.json").write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
print("attack_cases:", len(attack_cases), "by_variant:", dict(Counter(c["variant"] for c in attack_cases)))
print("tool_calls total:", len(base))
