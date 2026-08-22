# OPENCLAW_DEMO_CONFIG_REPORT

## 当前用户配置摘要

当前配置位于：

```text
C:\Users\ancientmoon\.openclaw\openclaw.json
```

关键现状：

```text
agents.defaults.workspace = E:\GovAgent-demo
tools.profile = coding
tools.exec.ask = off
tools.exec.security = full
plugins.entries.govagent-shield.enabled = true
mcp = 未配置
```

## 修改项

新增 Demo 专用配置：

```text
benchmark/e2e_real/config/demo_openclaw.json
```

修改内容：

- workspace 固定为 `E:\GovAgent-demo`
- tool profile 固定为 `minimal`
- `alsoAllow` 固定为 `read / exec / secure_upload_file`
- MCP 注册 `secure-upload-file` server
- 插件 endpoint 固定为 `http://127.0.0.1:8010`（Demo 专用引擎实例）

配置校验：

```text
openclaw config validate --json
{"valid": true, "warnings": []}
```

## 启用工具

```text
read
exec
secure_upload_file
```

## 禁用工具

```text
memory_search
memory_get
web_search
web_fetch
search
apply_patch
write
edit
process
session_status
message
sessions_list
sessions_history
sessions_search
sessions_send
```

## 使用方式

以 Demo 配置启动 OpenClaw：

```powershell
$env:OPENCLAW_CONFIG_PATH = "E:\Openclaw项目\揭榜挂帅\揭榜挂帅项目主体\GovAgent-Shield\benchmark\e2e_real\config\demo_openclaw.json"
```

## 说明

该配置为 benchmark 专用覆盖配置，不修改用户原始 `openclaw.json`。
