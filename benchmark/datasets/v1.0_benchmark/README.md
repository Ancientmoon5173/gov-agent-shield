# GovAgent-Shield Benchmark v1.0（正式基线，冻结）

- 冻结日期：2026-09-08 · 数据范围：benchmark/ 目录（全合成，不触碰 src/）
- 规模：100 条（benign 33 / controlled_attack 67）
- 变体：{'N': 14, 'P': 26, 'A': 15, 'S': 19, 'C': 21, 'E': 5}
- 每场景：{'S01': 13, 'S02': 13, 'S03': 13, 'S04': 13, 'S05': 12, 'S06': 12, 'S07': 12, 'S08': 12}

## 目录
- cases/cases.json：完整结构化 Case（schema 元数据齐全）
- engine_trio/：旧 runner 兼容三件套（attack/normal/expected）
- validation/：dry-run 回验原始数据 + 逐案校准记录
- reports/：旧 runner 全量指标 + 分项汇总 + RUN_REPORT

## 核心指标（旧 run_engine_benchmark.py 全量，临时审计库）
accuracy 1.0 / recognition 1.0 / blocking 1.0 / precision 1.0 / recall 1.0 / FPR 0 / audit_completeness 1.0

## 运行命令
```bash
# 一键（封装旧 runner + 汇总）：
bash benchmark/run_benchmark.sh
# 手动旧 runner（需临时替换其 BENCHMARK_DIR 或先复制 trio）：
python benchmark/runners/run_engine_benchmark.py
```
engine_trio 可直接被 run_engine_benchmark.py 加载（零代码修改）；`--emit-legacy-trio` 逻辑保留在 generator 中，默认不覆盖根目录三件套。

## 已知边界（如实）
1. P 变体 = CRITICAL 资产风险层模拟越权（permission_semantic_only=true），非原生权限拦截（legacy runner 固定 admin_agent）。
2. E/C 双路径：部分由 DPT 令牌泄漏 block，部分由 BehaviorAnalyzer 行为链 kill（dpt_detection_rate≈0.65），事件逐案校准、不强行统一。
3. benign 占比 33%（建议后续扩到 ≥40%）。
4. S07 人事 business=CRITICAL 但 engine 仅 SENSITIVE（confidential/），差异已记录于 fixture metadata。
