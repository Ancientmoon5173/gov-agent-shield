# Audit Phase1（Session/Chain/Call 结构化 + 因果链）实施记录

- 日期：2026-09-05
- 关联：docs/Audit_结构化重构方案_Phase1-2_2026-09-05.md（设计稿）
- 原则：增量修改；不破坏现有 API / V1 逻辑 / 测试语义；每阶段全量 pytest
- 结果：全量 pytest **164 passed**（159 原有 + 5 新增 Phase1 测试）

## S1 Schema：security_events 追加因果列
- `parent_event_id TEXT`、`trigger_event_id TEXT` + 索引 idx_se_parent / idx_se_trigger
- `audit_approvals` 追加 `event_uuid TEXT`
- 全部 ALTER 追加，旧行留空，向后兼容

## S2 Schema：薄聚合表
- 新建 `audit_sessions`（session_id PK, task_id, user_id, started_at, ended_at, status）
- 新建 `audit_chains`（chain_id PK, session_id, chain_type, started_at, ended_at, final_risk, final_disposition, status）
- 新建 `audit_calls`（call_id PK, session_id, chain_id, seq_no, tool_name, started_at, ended_at, decision, execution_status, parent_call_id）
- 新建 `risk_escalations`（from/to event_uuid, from/to score, delta, dominant_dimension, trigger_reason, decision, timestamp）
- 索引：chains.session、calls.chain/session、escalations.chain

## S3 写入逻辑（SecurityLogger，增量）
- `log_check` 新增 parent_event_id/trigger_event_id 参数与落列；
  - parent = 本调用内上一条事件（active.last_event_uuid）
  - trigger = `_resolve_trigger_event()` 按业务规则显式确定（不依赖物理行序）
- `_housekeep_after_event`：维护内存锚点（input/asset/data/decoy_hint/decoy_route/dpt_inject/dpt_leak/permission/behavior）+ active 上一步指针
- `_on_decision_event`（step=90）：写/更新 audit_calls；更新 audit_chains 终态与 chain_type；决策间风险/处置升级时写 risk_escalations
- `_chain_type_for_decision`：session/prompt_injection/permission/behavior_chain→(data_exfiltration|critical_asset|high_asset)/dpt_leak
- `open_call` 建 session/chain 行；resolve_approval/log_execution_outcome 回填 audit_approvals.event_uuid、更新 audit_calls 终态/ended_at
- 聚合维护失败不影响事件落库（try/except + 打印警告）

## S4 因果规则与测试
- 决策行 trigger：优先“上一决策”锚点（read→upload），否则本调用风险锚点
- 审批/执行事件 trigger：显式指向本 call 决策事件
- 新增 tests/test_audit_phase1_graph.py（5 项）：聚合表写入、因果边、风险升级 delta、审批 event_uuid 回填、kill call ended_at

## S5 查询/API
- SecurityLogger.get_escalations(session/chain) / get_audit_tree(session)：组装 Session→Chain→Call→Event + causal_path（trigger/parent 反向回溯，按事件 id 排序）
- 新增 FastAPI：GET /audit/session/{session_id}/tree、GET /audit/session/{session_id}/escalations（旧 API 不变）

## S6 UI 审计回放升级（中英双语）
- 全部事件类型/状态值“英文（中文）”展示
- 因果链面板：每个 block/kill 决策展示“为什么最终 BLOCK/KILL”的因果步骤链
- 风险升级表：from→to (Δ)、主导维度、触发决策、原因
- 每个 Call 步骤表增加 会话ID / 父事件 / 触发事件 溯源列

## S7 验证
- 全量 pytest 164 passed
- 冒烟（Phase1 Golden Path）：chain_type=data_exfiltration、final=kill@0.85、
  升级 0.595→0.85 Δ0.255 dominant=R_tool、kill 决策 causal_path 含 read 决策
- 回放页 AppTest 无异常；/audit/session/{sid}/tree、/escalations 均 200

## 与方案决策一致
1. Chain 不做物理拆分（session=1 chain；chain_type+trigger+escalations 表达阶段/因果）
2. 建三张薄聚合表，security_events 仍为唯一事实源
3. audit_fields 未建（Phase3）
4. Chain/session 默认 OPEN；仅 block/kill 等可靠终态写 call ended_at；不猜测 session-end
