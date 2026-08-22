# Real OpenClaw E2E Benchmark

验证 OpenClaw Agent -> Plugin Hook -> Security Engine 的真实链路。

## 运行

模拟链路（固定 Agent trace）：

```powershell
venv\Scripts\python benchmark\e2e_real\run_real_openclaw.py --mode simulated
```

真实 OpenClaw：

```powershell
venv\Scripts\python benchmark\e2e_real\run_real_openclaw.py --mode real
```

自动模式：优先真实链路，失败时降级为模拟链路：

```powershell
venv\Scripts\python benchmark\e2e_real\run_real_openclaw.py --mode auto
```

## 输出

- `outputs/agent_trace.json`
- `outputs/audit_trace.json`
- `outputs/e2e_report.json`
- `outputs/real_e2e_report.json`

## 真实/模拟区分

每个 case 的 `verification_mode` 字段：

- `real_openclaw`：真实 OpenClaw Agent + Plugin Hook + Security Engine
- `simulated_testclient`：TestClient + 固定 Agent trace

## Workspace

固定 fixture 由 `prepare_workspace.py` 写入
`E:\GovAgent-demo\demos`。

## 当前限制

- 真实 OpenClaw 使用真实 LLM，Agent 行为不完全确定，可能不读取预期文件。
- 当前真实链路已证明 Plugin Hook 被触发并产生审计，但 5 个场景的
  “预期 ToolCall 序列”依赖固定环境收敛。
- 外发类工具在真实 coding profile 中不存在，需测试 MCP tool 或
  `exec` 模拟。
