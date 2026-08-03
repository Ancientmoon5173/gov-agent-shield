# GovAgent-Shield OpenClaw 插件

将 GovAgent-Shield Python 安全服务作为 **Runtime Security Layer** 接入
OpenClaw，在真实工具执行前完成 allow / block / kill / review 决策。

## 接入方式

本目录是 OpenClaw 原生插件（`extensions/govagent-shield`）。

1. 启动 Python 安全服务：

   ```bash
   cd E:\Openclaw项目\揭榜挂帅\揭榜挂帅项目主体\GovAgent-Shield
   venv\Scripts\python -m uvicorn src.main:app --port 8000
   ```

2. 将插件部署到 OpenClaw：

   ```bash
   Copy-Item -Recurse openclaw_plugin\govagent-shield D:\OpenClaw\openclaw-main\extensions\govagent-shield
   ```

3. 在 OpenClaw 配置中启用插件（默认启用）：

   ```jsonc
   {
     "plugins": {
       "entries": {
         "govagent-shield": {
           "enabled": true,
           "options": {
             "endpoint": "http://127.0.0.1:8000",
             "timeoutMs": 5000,
             "failClosed": true
           }
         }
       }
     }
   }
   ```

## 数据流

```
OpenClaw Agent 生成 ToolCall
        ↓
before_tool_call hook（本插件）
        ↓
ToolRequest { session_id, agent_id, tool_name, parameters, context }
        ↓
POST http://127.0.0.1:8000/security/check_tool
        ↓
SecurityOrchestrator 完整安全链路
        ↓
allow → 继续执行原工具
block / kill / review → 返回 { block: true, blockReason }
        ↓
OpenClaw 跳过工具执行并返回阻断结果
```

## 组合模式说明

OpenClaw 会顺序执行所有插件的 `before_tool_call`，并将结果合并；
任一个插件返回 `block=true` 即短路，其他插件和原工具不再执行。
本插件因此只返回自己的决策，不需要也不应该手动调用“原 hook”。

## 安全策略

- 未知 action 默认 `block`
- HTTP 异常 / 超时默认 `block`（`failClosed=true`）
- `failClosed=false` 时服务不可用降级放行（仅用于联调）
- `review` 当前阶段按 `block` 处理，后续可映射到 OpenClaw 原生
  `requireApproval` 审批流程

## 测试

```bash
cd D:\OpenClaw\openclaw-main
node_modules\.bin\vitest.cmd run extensions/govagent-shield/test/hooks.test.ts
node_modules\.bin\vitest.cmd run extensions/govagent-shield/test/openclaw.runtime.test.ts
```

运行时测试会启动真实 OpenClaw `before_tool_call` 包装器，并通过 HTTP
调用真实 Python 安全服务，验证 allow / block / kill 三条路径。
