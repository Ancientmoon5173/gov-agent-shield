# Fixed ToolCall Security Benchmark（固定 ToolCall 攻击基准）

- 定位：Experiment B（受控变量评估 Shield 检测/处置），非真实 Agent E2E；不涉及模型自主拒绝。
- 数据集：attack_cases.json（100 条，复用 v1.0 engine ground-truth；N14/S19/P26/E5/C21/A15）
- Ground Truth：由场景定义 + 规则（DataClassifier 词表 / AssetResolver / Behavior/DPT 语义）推导，不由 LLM 生成。
- Baseline：baseline_results.json = 固定 ToolCall 无防护 replay，统一 BASELINE_REPLAY_WOULD_EXECUTE，execution_observed=false。
- Shield：shield_results.json = 真实 SecurityOrchestrator/check_tool_call（临时审计库）逐 call 结果。
- 指标：metrics.json / evaluation_report.md；verified dangerous execution = NOT MEASURED（engine-level replay）。
- 复现：python build_dataset.py → run_shield_eval.py → evaluate.py；校验：python validate_dataset.py
