# PLUGIN_STATUS_REPORT

只读检查时间：2026-08-21

## 1. 插件状态

- 配置：`plugins.entries.govagent-shield.enabled = true`
- 部署目录：`D:\OpenClaw\openclaw-main\extensions\govagent-shield`
- 部署目录中存在 `index.ts / hooks.ts / tool_request.ts / http_client.ts`
- 当前仓库与部署目录的 `hooks.ts` SHA256 不一致，部署版本早于仓库近期修改

## 2. before_tool_call

- 是：`hooks.ts` 构造 `ToolRequest` 后调用
  `ShieldHttpClient.sendToolRequest()`
- 最终请求：`POST {endpoint}/security/check_tool`
- 默认 endpoint：`http://127.0.0.1:8000`
- fail-close：网络异常 / 未知 action 默认 block

## 3. tool_result_persist

- 是：支持 `inject_token` 注入
- 逻辑：`pendingInjections` 保存令牌，`tool_result_persist` 在
  `role == "toolResult"` 消息内容末尾追加数据校验标记

## 4. after_tool_call

- 部分：当前只输出控制台日志
  `after_tool_call: durationMs / error`
- 未接入：没有调用 `/security/check_output`
- 未接入：没有把工具执行结果写入 SQLite 审计

## 5. 结论

插件 Hook 已具备真实拦截能力，但文档内容污染检测和输出审计仍需
通过测试脚本或插件适配层补充。

## 6. 实测证据（Phase 4.3-C）

真实 OpenClaw Agent 运行中，插件日志出现：

```text
[GovAgentShield] 捕获 ToolCall: read
[GovAgentShield] 捕获 ToolCall: exec
[GovAgentShield] audit warn: policy=disposition:warn
[GovAgentShield] after_tool_call
```

同时 SQLite 审计中出现对应 `tool_call` 事件，证明
`OpenClaw Agent -> Plugin Hook -> /security/check_tool -> SecurityEngine`
链路真实触发。
