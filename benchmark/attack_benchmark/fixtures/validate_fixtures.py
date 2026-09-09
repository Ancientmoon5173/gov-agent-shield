# -*- coding: utf-8 -*-
"""轻量 Fixture 校验（只读，不依赖 src；不修改 runner/源码）。

检查项：
1 YAML 语法  2 文件存在  3 fixture_id 唯一  4 scenario_id 合法
5 path 唯一   6 synthetic_only=true  7 文件可读
8 engine trigger 与 scenario library 一致(路径 marker→level)
9 asset_path_template 能解析到文件(目录 token 命中)
10 S01–S08 至少一个 fixture
"""
import pathlib, sys, yaml

HERE = pathlib.Path(__file__).resolve().parent
FIX = HERE / "fixture_library.yaml"
SCN = HERE.parent / "scenarios" / "scenario_library.yaml"
ALLOWED_SID = {f"S{i:02d}" for i in range(1, 9)} | {"SHARED"}
MARKER_LEVEL = {"top_secret": "CRITICAL", "secret": "SENSITIVE", "confidential": "SENSITIVE", "internal": "INTERNAL"}

def main():
    errs, warns, infos = [], [], []
    lib = yaml.safe_load(FIX.read_text(encoding="utf-8"))
    scn_lib = yaml.safe_load(SCN.read_text(encoding="utf-8")) if SCN.exists() else {"scenarios": []}
    fixtures = lib["fixtures"]
    # 3/5 id/path 唯一
    ids = [f["fixture_id"] for f in fixtures]
    paths = [f["path"] for f in fixtures]
    if len(ids) != len(set(ids)): errs.append("duplicate fixture_id")
    if len(paths) != len(set(paths)): errs.append("duplicate path")
    # 4 scenario 合法 & 10 覆盖
    by_sid = {}
    for f in fixtures:
        sid = f["scenario_id"]
        if sid not in ALLOWED_SID:
            errs.append(f"{f['fixture_id']}: scenario_id {sid} 非法")
        by_sid.setdefault(sid, []).append(f["fixture_id"])
        # 6
        if f.get("synthetic_only") is not True:
            errs.append(f"{f['fixture_id']}: synthetic_only != true")
        # 2/7 文件存在可读
        p = HERE / f["path"]
        if not p.exists():
            errs.append(f"{f['fixture_id']}: 文件不存在 {f['path']}")
        else:
            try:
                p.read_text(encoding="utf-8")
            except Exception as e:
                errs.append(f"{f['fixture_id']}: 文件不可读 {e}")
        # 8 marker→level 一致性
        lvl = f["engine_classification"]["level"]
        for m in f["engine_classification"].get("path_markers", []) + f.get("asset_path_tags", []):
            expect = MARKER_LEVEL.get(m)
            if expect and expect != lvl:
                errs.append(f"{f['fixture_id']}: marker {m} 应映射 {expect}，声明 {lvl}")
        if lvl == "PUBLIC":
            low = (f["path"] or "").lower()
            if any(k in low for k in ("top_secret", "secret", "confidential", "internal")):
                errs.append(f"{f['fixture_id']}: 声明 PUBLIC 但路径含敏感 marker")
    for s in range(1, 9):
        sid = f"S{s:02d}"
        if sid not in by_sid or not by_sid[sid]:
            errs.append(f"{sid}: 无 fixture")
    # 9 asset_path_template 目录 token 命中（exclude SHARED）
    scn_by_id = {s["scenario_id"]: s for s in scn_lib.get("scenarios", [])}
    for s in range(1, 9):
        sid = f"S{s:02d}"
        sc = scn_by_id.get(sid, {})
        templates = ((sc.get("data") or {}).get("engine_classification") or {}).get("asset_path_template", []) or []
        if not templates:
            continue
        tokens = []
        for t in templates:
            seg = t.split("/")[0].replace("*", "").strip()
            if seg:
                tokens.append(seg)
        hit = False
        for fid in by_sid.get(sid, []):
            fp = next(f for f in fixtures if f["fixture_id"] == fid)["path"].lower()
            if any(tok.lower() in fp for tok in tokens):
                hit = True
                break
        if not hit:
            warns.append(f"{sid}: asset_path_template {templates} 未命中任何 fixture 路径（token={tokens}）")
    infos.append(f"fixtures={len(fixtures)} scenarios_covered={sorted(s for s in ALLOWED_SID if s != 'SHARED' and by_sid.get(s))}")
    print("ERRORS:", errs if errs else "none")
    print("WARNINGS:", warns if warns else "none")
    print("INFO:", infos)
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
