# -*- coding: utf-8 -*-
"""validate_dataset.py — 数据集自检（PASS/FAIL）。"""
import json, pathlib, re, sys
AB = pathlib.Path(__file__).resolve().parent
cases = json.loads((AB/"attack_cases.json").read_text(encoding="utf-8"))
exp = json.loads((AB/"expected_results.json").read_text(encoding="utf-8"))["cases"]
shield = json.loads((AB/"shield_results.json").read_text(encoding="utf-8"))
baseline = json.loads((AB/"baseline_results.json").read_text(encoding="utf-8"))
TOOLS = {"read","read_document","search","search_knowledge_base","generate_summary","generate_report",
         "query_citizen_info","upload_data","upload_file","send_email","http_request","exec","write_file","share_internal"}
errs=[]
ids=[c["case_id"] for c in cases]
if len(ids)!=len(set(ids)): errs.append("case_id duplicate")
for c in cases:
    if c["scenario_id"] not in {f"S{i:02d}" for i in range(1,9)}: errs.append(f"{c['case_id']} bad scenario")
    if c["variant"] not in ["N","S","P","E","C","A"]: errs.append(f"{c['case_id']} bad variant")
    if c["case_id"] not in exp: errs.append(f"{c['case_id']} missing expected")
    for t in c["tool_calls"]:
        if t["tool"] not in TOOLS: errs.append(f"{c['case_id']} bad tool {t['tool']}")
    for f in c["fixture_refs"]:
        if not (AB/"fixtures"/f).exists(): errs.append(f"{c['case_id']} fixture missing {f}")
# sensitive ground truth ↔ expected class
for c in cases:
    e = exp[c["case_id"]]
    if c["ground_truth"]["requires_sensitive_asset"] and e["expected_data_class"]=="PUBLIC":
        errs.append(f"{c['case_id']} sensitive GT but PUBLIC class")
# external GT ↔ has exfil tool external
EXT_MARK=["http://","https://","@","collect.example","example.com","ftp://"]
for c in cases:
    if c["ground_truth"]["requires_external_transfer"]:
        ok=any(t["tool"] in {"upload_data","upload_file","send_email","http_request"} and any(m in json.dumps(t["params"],ensure_ascii=False).lower() for m in EXT_MARK) for t in c["tool_calls"])
        if not ok: errs.append(f"{c['case_id']} external GT but no external op")
# multi-step chain check (C cases should have >=2 calls)
for c in cases:
    if c["variant"]=="C" and len(c["tool_calls"])<2: errs.append(f"{c['case_id']} C not multi-step")
# PII scan in fixtures
id_re=re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"); ph_re=re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
for p in (AB/"fixtures").rglob("*"):
    if p.is_file():
        try: txt=p.read_text(encoding="utf-8",errors="ignore")
        except Exception: continue
        if id_re.search(txt): errs.append(f"possible real ID in {p}")
        if ph_re.search(txt): errs.append(f"possible real phone in {p}")
# baseline vs shield input identical
bkey=[(b["case_id"],b["tool_call_id"],b["tool"]) for b in baseline]
skey=[(s["case_id"],s["tool_call_id"],s["tool"]) for s in shield]
if bkey!=skey: errs.append("baseline/shield inputs differ")
print("VALIDATION:", "PASS" if not errs else "FAIL")
for e in errs[:20]: print(" -", e)
