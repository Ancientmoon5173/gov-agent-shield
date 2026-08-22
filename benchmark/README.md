# GovAgent-Shield Security Benchmark

面向国赛展示的 Agent 安全能力量化评估框架。只调用现有
`SecurityOrchestrator`，不复制安全逻辑，不修改核心模块。

## 样本

- `attack_cases.json`：30 个攻击样本，覆盖
  `prompt_injection / sensitive_asset_access / credential_access /
  unauthorized_exfiltration / tool_chain_abuse`
- `normal_cases.json`：20 个正常样本，覆盖
  `normal_query / report_generation / data_sharing`
- `expected_result.json`：每个样本的期望决策、期望阻断与必需审计事件

## 运行

```powershell
venv\Scripts\python benchmark\runners\run_engine_benchmark.py
```

仅运行前 N 个样本：

```powershell
venv\Scripts\python benchmark\runners\run_engine_benchmark.py --limit 5
```

运行 Decoy ABC 专项验证：

```powershell
venv\Scripts\python benchmark\runners\run_decoy_abc_benchmark.py
```

## 输出

- `outputs/raw_results.json`：每个样本的 ToolCall、action、risk、
  policy_id、audit events、latency
- `outputs/metrics_report.json`：六项指标 + 性能统计
- `outputs/audit_field_report.json`：普通 tool / Decoy / DPT 事件字段级校验
- `outputs/decoy_abc_report.json`：Shadow Route、Behavioral Decoy、DPT 专项结果

## 指标口径

- Recognition Rate：攻击 ToolCall 中产生非 ALLOW 决策的比例
- Blocking Rate：期望阻断攻击中实际 block/kill 的比例
- Precision / Recall / FPR：基于 block/kill 的混淆矩阵
- Audit Completeness：必需审计事件命中比例
- Detection Rate：攻击样本中产生非 ALLOW 决策的比例
- Mitigation Rate：block/kill 或 review 后 deny/terminate 的缓解比例
- Review Rate：最终 action 为 review 的攻击样本比例
- Escalation Rate：review 后续变为 deny/terminate/block 的比例
- Decoy Route Success Rate：成功重定向到诱饵副本的比例
- DPT Detection Rate：DPT 泄漏尝试中被检测阻断的比例
- model_refusal_rate：预留字段，引擎级 benchmark 固定为 0

## 设计约束

- 不改 Decision Contract
- 不改 RiskEngine / DispositionEngine
- 不改 Decoy 逻辑
- 不新增安全模块
