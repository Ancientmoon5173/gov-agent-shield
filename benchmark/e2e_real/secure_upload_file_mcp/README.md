# secure_upload_file MCP

模拟外发工具，用于真实 OpenClaw Demo C。

## 注册方式

将 `openclaw.mcp.json` 中的 `mcp.servers.secure-upload-file` 合并到
OpenClaw 用户配置后重启 Gateway。

## 工具参数

```json
{
  "file": "数据库连接配置.txt",
  "destination": "external"
}
```

## 设计约束

- 不真正外发数据。
- 工具调用前必须经过 GovAgent-Shield `before_tool_call`。
- 安全决策为 block 时，工具不会真正执行。
