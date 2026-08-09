# GovAgent-Shield OpenClaw 适配层

> **DEPRECATED**
>
> 该模块为早期实验方案，已不再作为正式接入方式。
> 当前正式方案是 OpenClaw 原生插件：
>
> ```text
> openclaw_plugin/govagent-shield
> ```
>
> 请勿再修改 `agent-harness.ts` 来注入本适配器；新项目请直接使用
> `openclaw_plugin/govagent-shield`。本目录仅作历史参考保留。

## 目标

将 GovAgent-Shield 作为 Runtime 安全层接入 OpenClaw Agent。

```
OpenClaw ToolCall
    ↓
GovAgent-Shield Adapter (本目录)
    ↓
HTTP 调用 Python 安全服务 (Phase 2)
```

## Phase 1（当前）

- 创建 hooks 适配文件
- 捕获 OpenClaw ToolCall
- 输出完整 ToolRequest 日志
- **不接入安全阻断逻辑**

## 文件结构

```
openclaw_adapter/
├── package.json          # npm 配置
├── tsconfig.json         # TypeScript 配置
├── src/
│   ├── index.ts          # 导出入口
│   ├── types.ts          # ToolRequest + OpenClaw 上下文类型
│   ├── tool_request.ts   # OpenClaw → ToolRequest 构建器
│   ├── hooks.ts          # beforeToolCall / afterToolCall 钩子
│   └── http_client.ts    # HTTP 客户端（Phase 2 预留）
├── test/
│   └── hooks.test.ts     # 适配层测试
└── README.md
```

## 接入 OpenClaw（历史参考，已不推荐）

> 注意：以下内容仅为早期实验记录，不推荐按此方式修改
> `agent-harness.ts`。正式接入请使用 `openclaw_plugin/govagent-shield`。

### 1. 安装依赖

```bash
cd openclaw_adapter
npm install
```

### 2. 在 OpenClaw harness 中注册 hooks

在 `agent-harness.ts` 的 `createLoopConfig()` 中注入：

```typescript
import { createGovAgentShieldHooks } from "govagent-shield-openclaw-adapter";

// Phase 1: 仅捕获 + 日志
const shieldHooks = createGovAgentShieldHooks({
  sessionId: "session-id",
  agentId: "agent-id",
});

// Phase 2: 启用 HTTP 调用
// const shieldHooks = createGovAgentShieldHooks({
//   sessionId: "session-id",
//   agentId: "agent-id",
//   httpClient: new ShieldHttpClient({ endpoint: "http://127.0.0.1:8000", enabled: true }),
// });

// 在 createLoopConfig 中合并 hooks
const loopConfig = {
  ...baseConfig,
  beforeToolCall: async (ctx) => {
    const shield = await shieldHooks.beforeToolCall(ctx);
    if (shield?.block) return shield; // Phase 2 阻断
    return originalBeforeToolCall?.(ctx);
  },
  afterToolCall: async (ctx) => {
    const shield = await shieldHooks.afterToolCall(ctx);
    if (shield) return shield; // Phase 2 脱敏
    return originalAfterToolCall?.(ctx);
  },
};
```

### 3. 运行测试

```bash
node test/hooks.test.ts
# 或
npx tsx test/hooks.test.ts
```

## ToolCall 数据流

```
OpenClaw beforeToolCall 触发
    ↓
ctx.toolCall.name / ctx.args
    ↓
buildToolRequest(ctx, sessionId, agentId)
    ↓
ToolRequest {
  session_id,
  agent_id,
  tool_name,
  parameters,
  context: { message_id, assistant_message, tool_arguments_raw },
  timestamp
}
    ↓
console.log 输出完整 ToolRequest
    ↓
Phase 2: ShieldHttpClient.sendToolRequest() → Python 安全服务
```

## Phase 2 规划

- 启用 `ShieldHttpClient` 实际 HTTP 调用
- 根据安全服务返回决策：
  - `allow` → 放行
  - `block` / `kill` → 返回 `{ block: true, reason }`
  - `review` → 返回 `{ block: true, reason: "需要审批" }`
- `afterToolCall` 集成输出脱敏
