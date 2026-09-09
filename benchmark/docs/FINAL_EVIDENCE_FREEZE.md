# FINAL_EVIDENCE_FREEZE — 100 条真实 E2E 证据冻结

> 性质：只读证据快照（2026-09-09）。原始证据一律未覆盖；本文件仅为分类索引。

## A. 已真实观测的 E2E 结果（Experiment A）
- 100/100 valid；TOOL_CALL_GENERATED=100；RUN_ENV_FAILURE=0；MODEL_AVOIDANCE=0
- 变体：N14/S19/P26/E5/C21/A15；e2e_verdict SUCCESS 66 / FAILURE 34（FAILURE 全部为 REVIEW headless 未决）
- Shield（危险语义 call）：BLOCK 104 · REVIEW 37 · ALLOW/WARN 8；Conditional Blocking = 0.698
- 真实危险执行：verified dangerous execution = 0（E2E ASR = 0.0，分母 149）
- benign FP = 2（S08-N-001, S08-S-001）
- engine↔E2E：comparable 66，match 43 / mismatch 23 → 0.6515

## B. 固定 ToolCall 基准结果（Experiment B，见 benchmark/attack_benchmark）
- 构造式 Engine-level Replay；Shield 决策来自真实 SecurityOrchestrator/check_tool_call（临时审计库）。
- 该基准不涉及 Agent 自主拒绝；MODEL_AVOIDANCE 不进入其指标。

## C. 构造式 baseline/replay 结果（Experiment C）
- No-Shield Baseline = 固定 ToolCall 无防护路径的 replay 语义：统一记 `BASELINE_REPLAY_WOULD_EXECUTE`，execution_observed=false。
- 不是第二次真实 Agent E2E；不虚构执行证据。

## D. 计划性实验（不得伪装为已完成）
- No-Shield 原生 Agent 100 条对照组：未运行（成本/网络限制），仅以固定 ToolCall replay 替代。
- REVIEW→approve 通道的 E2E 闭环：未完成（headless 审批未决）。

## 证据文件索引
- 核心：final_100_aggregate.json · final_100_compare_engine_e2e.json · final_100_strict_metrics.json · final_100_strict_attribution_report.md
- 逐 case：outputs/{smoke_100_1, e2e_batch1_20, e2e_batch1_rest, e2e_remain_*, rerun_smoke, rerun_probe, rerun_51_fore_a, rerun_31_fore_a, rerun_31_fore_b}/case_*/
- 归档：_legacy_first_pass_failed/
