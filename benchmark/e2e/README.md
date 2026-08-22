# E2E Agent Benchmark

本目录用于验证 OpenClaw Plugin -> Security Engine 的最小可复现链路。

## 调用链

```text
固定用户输入
  -> 固定 Agent trace（expected_tool_plan）
  -> OpenClaw Plugin 契约 ToolRequest
  -> HTTP POST /security/check_tool
  -> SecurityOrchestrator
  -> RiskEngine + DispositionEngine
  -> Decision
  -> allow/warn 执行下一步
     review + auto-deny 记录 review_denied
     block/kill 终止
  -> SecurityLogger audit events
```

## 场景

- `E2E-N-001`：正常政企业务，最终 `engine_allow`
- `E2E-A-001`：间接提示注入，最终 `engine_block`
- `E2E-R-001`：人工审批，管理员 deny，最终 `review_denied`
- `E2E-N-002`：模型不调用工具，`no_tool_call`

## 记录字段

每个 case 输出：

```text
user_input
document_context
input_context
agent_trace
tool_calls
security_decisions
audit_events
audit_event_records
result_type
final_action
```

## 指标输出

```text
outputs/e2e_raw_results.json
outputs/e2e_metrics_report.json
```

## 限制

- 使用固定 prompt 和固定 Agent trace，不调用真实随机 LLM。
- 通过 FastAPI TestClient 模拟 Plugin HTTP 调用，不启动真实 OpenClaw 二进制。
- 审批行为由 `approval_mode` 模拟：`auto-allow` / `auto-deny`。
