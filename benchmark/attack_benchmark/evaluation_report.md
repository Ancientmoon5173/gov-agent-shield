# Fixed ToolCall Security Benchmark — Evaluation Report
- total cases: 100；by variant: {'N': 14, 'P': 26, 'A': 15, 'S': 19, 'C': 21, 'E': 5}；tool calls: 161
- dangerous toolcalls: 67（block 67 / review 0 / residual allow 0）
- DBR = 1.0；review rate = 0.0；residual allow = 0.0
- false positives（benign N+S 被 block/kill）: []（rate 0.0）
- verified dangerous execution: NOT MEASURED（engine replay；Experiment A E2E verified=0）
- Baseline：BASELINE_REPLAY_WOULD_EXECUTE（非真实执行，execution_observed=false）
