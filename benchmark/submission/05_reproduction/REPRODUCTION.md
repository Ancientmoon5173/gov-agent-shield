# REPRODUCTION

## 可直接复现的 Engine Benchmark（低外部依赖）
- Python 3.11；依赖见 requirements.txt（fastapi/uvicorn/pyyaml 等，运行 venv）
- 步骤：
  1) python benchmark/attack_benchmark/build_dataset.py
  2) python benchmark/attack_benchmark/run_shield_eval.py
  3) python benchmark/attack_benchmark/evaluate.py
  4) python benchmark/attack_benchmark/validate_dataset.py
- 查看：metrics.json / evaluation_report.md；审计日志：data/audit_logs/security_events.db（临时库在 run_shield_eval 中自动使用）

## Real E2E（高外部依赖，成本高，非本源码仓库的复现目标）
- 需要本地 OpenClaw 2026.7.2（Node ≥18）+ 模型 provider key（DeepSeek）+ 本地引擎 8000（single_user）+ synthetic fixtures。
- 100/100 等真实 E2E 结果与限定口径已冻结于 benchmark/docs/FINAL_METRICS_TABLE.md 与 FINAL_EXPERIMENT_FACT_SHEET.md；原始逐 case evidence 不随源码仓库分发。
注意：Engine Benchmark 与 Real E2E 复现成本不同，不能等同声明。
