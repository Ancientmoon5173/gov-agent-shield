# GovAgent-Shield OpenClaw 插件

将 GovAgent-Shield Python 安全服务作为 **Runtime Security Layer** 接入
OpenClaw：在真实工具执行前完成安全检测，并根据统一决策放行或阻断。

---

## 1. 插件作用

- 通过 OpenClaw 原生 `before_tool_call` Hook 捕获 ToolCall
- 将 ToolCall 转换为 ToolRequest 并调用 Python 安全服务
- 根据 `allow / warn / review / block / kill` 决策控制工具执行
- 记录决策日志与审计信息

插件只负责：

- Hook 拦截
- HTTP 协议转换
- 决策执行

插件不负责策略判断，所有风险分析由 Python
`SecurityOrchestrator` 完成。

---

## 2. 安装

### 方式 A：复制到 OpenClaw 扩展目录

```powershell
Copy-Item -Recurse openclaw_plugin\govagent-shield D:\OpenClaw\openclaw-main\extensions\govagent-shield
```

### 方式 B：通过 OpenClaw 配置启用

插件默认启用；如需显式配置，在 `openclaw.json` 中写入：

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

修改配置后重启 OpenClaw gateway。

---

## 3. 配置项

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `true` | 是否启用安全检测 |
| `endpoint` | `http://127.0.0.1:8000` | Python 安全服务地址 |
| `timeoutMs` | `5000` | 安全检测请求超时（毫秒） |
| `failClosed` | `true` | 服务不可用/未知动作时是否默认阻断 |

> 说明：manifest 中还声明了 `logLevel` 配置项，当前版本未参与日志过滤，仅为后续预留。

---

## 4. Hook 流程

```
OpenClaw Agent 生成 ToolCall
    ↓
before_tool_call Hook
    ↓
ToolRequest { session_id, agent_id, tool_name, parameters, context }
    ↓
POST http://127.0.0.1:8000/security/check_tool
    ↓
SecurityOrchestrator 完整安全链路
    ↓
Decision Contract { action, risk_score, reason, policy_id }
    ↓
执行 / 阻断
```

组合模式：OpenClaw 会顺序执行所有插件的 `before_tool_call` 并合并结果；
任一插件返回 `block=true` 即短路。本插件不需要手动调用其他 hook。

另外注册 `tool_result_persist`：当 Python 决策携带 `inject_token` 时，
插件在工具结果消息写入会话前追加数据溯源令牌，供外发边界扫描。

---

## 5. Decision Contract

Python 引擎返回统一动作，插件按以下规则执行：

| action | 插件行为 |
|---|---|
| `allow` | 放行，继续执行工具 |
| `warn` | 放行，同时记录审计日志 |
| `review` | 触发 OpenClaw 原生 `requireApproval` 审批（可放行/拒绝） |
| `block` | 触发 deny-only 审批弹窗（critical，仅可拒绝，拒绝后阻断） |
| `kill` | 触发 deny-only 审批弹窗并标记终止任务 |

fail-close 策略：

- 未知 action → `block`（`invalid_decision_contract`）
- 网络异常/超时 → `block`（`transport_failure`，deny-only 审批）
- `failClosed=false` 时服务不可用降级放行（仅用于联调）

---

## 6. 验证方法

### 确认插件已加载

```powershell
cd D:\OpenClaw\openclaw-main
node openclaw.mjs plugins list --json
```

输出中应包含：

```json
{
  "id": "govagent-shield",
  "enabled": true,
  "status": "loaded"
}
```

### 查看插件日志

正常工具调用会输出：

```
[GovAgentShield] 捕获 ToolCall: read_document
========== GovAgent Shield ==========
[Agent] ...
[ToolCall] tool: read_document
[Security] risk: 0.2
decision: ALLOW
=====================================
```

阻断时 `decision` 为 `BLOCK` / `KILL`，并带有 `reason`。

### 验证 ToolCall 被拦截

运行插件运行时测试：

```powershell
cd D:\OpenClaw\openclaw-main
node_modules\.bin\vitest.cmd run extensions\govagent-shield\test\openclaw.runtime.test.ts
```

测试覆盖三个场景：

- 普通读取 → allow，工具执行
- 敏感文件读取 → block，工具不执行
- 查询居民信息后上传 → kill，工具不执行

---

## 7. Troubleshooting

### 插件未加载

- 检查 `extensions/govagent-shield` 目录是否存在且包含 `index.ts`
- 检查 `openclaw.json` 中 `plugins.entries.govagent-shield.enabled` 是否为 `true`
- 运行 `node openclaw.mjs plugins list --json` 查看状态

### Python 服务未启动

- 插件会 fail-close：所有工具调用被阻断
- 检查 `http://127.0.0.1:8000/health` 是否返回 `healthy`
- 启动命令：

  ```powershell
  venv\Scripts\python -m uvicorn src.main:app --port 8000
  ```

### endpoint 错误

- 修改插件配置 `endpoint` 为正确地址
- 确认 Python 服务监听端口与配置一致
- 修改后重启 OpenClaw gateway

### 配置不生效

- 修改 `openclaw.json` 后需要重启 gateway
- 确认修改的是用户配置 `C:\Users\ancientmoon\.openclaw\openclaw.json`
- 如果运行的是构建产物，需重新构建插件 dist：

  ```powershell
  cd D:\OpenClaw\openclaw-main
  node scripts\tsdown-build.mjs
  ```
