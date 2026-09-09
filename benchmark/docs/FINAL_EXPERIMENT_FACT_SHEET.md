# FINAL_EXPERIMENT_FACT_SHEET（仅事实，可直接引用）

## Real E2E Facts（Experiment A）
- 100/100 valid；TOOL_CALL_GENERATED=100；MODEL_AVOIDANCE=0；RUN_ENV_FAILURE=0（证据：final_100_*）
- 真实危险语义调用 149：BLOCK 104 / REVIEW 37 / ALLOW·WARN 8；Conditional Blocking=104/149≈0.698
- 真实危险执行 verified=0（E2E Attack Success=0/149）
- benign FP=2（S08-N-001、S08-S-001，保留为限制）
- Engine-E2E：可比较 66 条，一致 43，不一致 23，一致性≈0.6515
- 34 条 E2E_FAILURE 全部为 REVIEW+headless 未决（非攻击成功、非漏报）

## Fixed Benchmark Facts（Experiment B）
- 100 case / 161 ToolCall / 危险 ToolCall 67 / BLOCK 67 → 危险 ToolCall Blocking Rate=100%（Engine-level Replay）
- REVIEW=0 · residual allow=0 · benign(N+S) FP=0
- 执行类结论：NOT MEASURED
- Shield 决策与 expected_results 相互独立

## Baseline Facts（Experiment C）
- No-Shield Baseline = 固定 ToolCall replay 语义：BASELINE_REPLAY_WOULD_EXECUTE，execution_observed=false
- 不是第二次真实 Agent 实验，不构成“攻击全部成功”

## Limitations
- REVIEW-approve E2E 闭环未实现（headless）
- No-Shield 原生 Agent 100 条未运行（以固定 replay 替代）
- E 类仅 5 条（真实外传语义受限）
- Engine-E2E 一致性 0.6515（差异根因为 HYPOTHESIS）
- payload 级“数据实际外发”无外部接收器证据（verified=0 为间接证据）

## Reproducibility
- Fixed benchmark：build_dataset.py → run_shield_eval.py → evaluate.py → validate_dataset.py（PASS）
- E2E：需本地 OpenClaw 2026.7.2 + DeepSeek key；逐 case evidence 冻结于 e2e_full_100/

## Metrics
100 / 149 / 104 / 37 / 8 / 0.698 / 0 / 2 / 66 / 43 / 23 / 0.6515 / 67 / 1.0 / NOT MEASURED
