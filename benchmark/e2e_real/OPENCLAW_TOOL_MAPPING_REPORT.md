# OPENCLAW_TOOL_MAPPING_REPORT

只读检查时间：2026-08-21

## 1. coding profile 已确认工具

- `read`
- `exec`
- `apply_patch`
- `write` / `edit` / `bash` 相关工具在 OpenClaw 源码中可见

## 2. 未确认工具

- `upload_file`：当前 OpenClaw 源码中未找到同名内置工具
- `send_email` / `http_request`：不是 coding profile 默认内置工具
- 引擎侧 `read_document / upload_data / query_citizen_info` 是项目 Demo
  工具名，不是 OpenClaw 内置工具

## 3. 测试替代方案

- 外发行为改用 `exec curl / Invoke-WebRequest` 模拟
- 或通过测试 MCP tool 提供 `secure_upload_file`
- Benchmark 固定 trace 中保留 `upload_file`，仅用于模拟 Plugin 契约验证；
  真实 OpenClaw 链路明确标注工具映射差异

## 4. 结论

真实 OpenClaw coding profile 可验证 `read` 等真实工具，但不能假设
`upload_file` 存在。真实 E2E 需要工具映射或测试 MCP tool。
