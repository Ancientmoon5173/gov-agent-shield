# EXPERIMENT_FINAL_AUDIT（论文/比赛评审视角自审）

## 文件清单
- 证据冻结：benchmark/docs/FINAL_EVIDENCE_FREEZE.md
- 固定基准：benchmark/attack_benchmark/{README, attack_cases, expected_results, baseline_results, shield_results, metrics, evaluation_report, evaluate.py, validate_dataset.py, build_dataset.py, run_shield_eval.py, fixtures/}
- 方案/视频：benchmark/docs/实验测试方案_v1.0.md · 演示视频素材与旁白.md
- 补充：benchmark/supplement/{README, dataset, evaluation, attack_examples, audit_examples, reproduction}

## 数据来源
- Experiment A：100 条真实 OpenClaw E2E（e2e_full_100/final_100_*，已冻结，未覆盖）
- Experiment B/C：v1.0 engine ground-truth 派生固定 ToolCall；Shield 结果由真实 check_tool_call（临时审计库）产生

## 实验类型与可追溯
- A：真实 E2E（observed） · B：Fixed ToolCall Engine-level Replay · C：Baseline Replay（WOULD_EXECUTE 语义）

## 指标口径
- 已验证：A 真实危险执行=0（verified）；B DBR=1.0、review/residual/FP（engine 确定性）
- 未测量：B 执行类（NOT MEASURED，非 0）；No-Shield 原生 Agent 100 条（未运行）
- 混淆防护：无 Agent refusal→Shield；无 ToolCall→attack success；无 replay→real execution

## 构造数据说明
- fixtures 全合成（SYNTH/DEMO 标注）；attack/expected 由规则（词表/资产/行为/DPT 语义）生成，无 LLM 生成 expected
- Baseline WOULD_EXECUTE 为 replay 语义，execution_observed=false

## 风险与限制
- REVIEW 在 headless 无审批通道 → pending（非 BLOCK）
- E 类仅 5 条（受真实可外发语义限制，未硬造）
- benign FP=2（S08-N/S-001）保留
- A↔E2E consistency 0.6515：差异主因 REVIEW/语义粒度，已在文档说明

## 自审 15 问结论
1 构造数据未写成真实实验（有类型标注）✅
2 baseline replay 未写成真实执行 ✅
3 Agent refusal 未计入 Shield ✅
4 ToolCall 生成 ≠ attack success ✅
5 未测量标 NOT MEASURED（非 0）✅
6 Ground Truth 非 LLM 生成 ✅
7 expected 与源码规则一致（validate PASS）✅
8 fixture 命中 trigger（validate 校验敏感↔class）✅
9 external case 均有外部操作（validate）✅
10 正常样本未误归 attack（variant 独立）✅
11 未改 src/ ✅
12 未覆盖真实 E2E 原始结果 ✅
13 数字可由 JSON 重算（evaluate.py）✅
14 文档数字取自 metrics/e2e JSON ✅
15 各文档口径一致（本轮校验）✅

## 建议
- Experiment A/B 可用于正式比赛材料；Experiment C 作为对照说明使用；
- E 类扩量与 REVIEW approve 通道列为后续 improvement target（诚实保留）。
