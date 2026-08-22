# EVIDENCE_FREEZE_REPORT

冻结版本：2026.08.22-demo-freeze

## Demo A evidence

- `demo_validation_raw.json`：DEMO-A 10 轮真实 ToolCall + Decision
- `DEMO_STABILITY_REPORT.md`：allow 10/10
- audit：`final_audit_trace.json`

## Demo B evidence

- `demo_validation_raw.json`：DEMO-B 10 轮真实 review
- `demo_B_review_flow.json`：human-in-the-loop deny
- audit：`asset_resolved / behavior_chain / decoy_virtual_hit`

## Demo C evidence

- `demo_validation_raw.json`：DEMO-C 10 轮真实 block
- audit：`asset_resolved / decoy_route_triggered / data_provenance_injected / behavior_chain`
- upload prevented：secure_upload_file 未执行

## metrics 文件

- `demo_metrics_report.json`
- overall_success_rate: 1.0

## audit 文件

- `final_audit_trace.json`
- `demo_validation_raw.json`（原始审计）

## plugin hash

- `D:\OpenClaw\openclaw-main\extensions\govagent-shield\src\hooks.ts`: `720c24befe5c8fd1...`

## workspace hash

| file | sha256 |
|---|---|
| `policy_document.txt` | `83e2e8ce4d94c814...` |
| `企业联系人信息.xlsx` | `fe641124b113ded2...` |
| `企业诉求汇总.docx` | `a046c5a4830c43dc...` |
| `园区企业季度服务数据.xlsx` | `2c75660719c4ce15...` |
| `园区企业服务报告.pdf` | `d2f3e8da14b55c2f...` |
| `数据库连接配置.txt` | `d89039401ccdc320...` |

## 证据状态

- Demo A/B/C 30/30 成功
- Demo-B 最终 `review_denied` 由人工 deny 完成
- secure_upload_file 为 config_only + simulation_only 验证