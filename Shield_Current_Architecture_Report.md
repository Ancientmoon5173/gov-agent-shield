# GovAgent-Shield 当前架构分析报告

> 版本：2026-08-08 ｜ 性质：只读架构分析（未修改任何代码）

---

## 1. 项目文件树

```
GovAgent-Shield/
├── src/
│   ├── main.py                    # FastAPI 入口：/agent/run、/security/check_tool、/security/check_output
│   ├── config.py                  # 全局配置：风险权重、阈值、security_mode、LLM 配置
│   ├── agent/
│   │   ├── agent.py               # GovAgent 主类：run()、planner/mock 执行、安全钩子
│   │   ├── planner.py             # 意图匹配 + ToolCall 生成（mock LLM 行为）
│   │   ├── tools.py               # 5 个政企工具：read/search/query/summary/upload
│   │   └── prompts.py             # 系统提示词
│   ├── security/
│   │   ├── orchestrator.py        # SecurityOrchestrator：唯一对外安全接口
│   │   ├── parameter_checker.py   # 参数风险检测（路径穿越/敏感词/批量/外传目标）
│   │   ├── behavior_analyzer.py   # 行为链分析（read→upload、批量、高频）
│   │   ├── decoy_manager.py       # 动态诱饵：风险信号源，不直接阻断
│   │   ├── output_guard.py        # 输出脱敏（身份证/手机号/API Key/内部标记）
│   │   ├── permission_checker.py  # 权限检查包装器（single_user/enterprise）
│   │   ├── security_logger.py     # SQLite 安全审计日志
│   │   └── tool_risk_config.py    # 工具基础风险表 + 参数规则
│   ├── input_guard/
│   │   ├── detector.py            # InputDetector：规则扫描
│   │   ├── rules.py               # Prompt Injection / 越狱 / 指令覆盖规则
│   │   └── sensitive_data_leak_detector.py  # 数据外泄三元组检测
│   ├── tool_gateway/              # 工具策略网关（规则策略，当前未主导决策）
│   ├── risk_engine/
│   │   ├── scorer.py              # RiskScorer：加权 + max 兜底
│   │   └── actions.py             # DispositionEngine：allow/warn/review/block/kill
│   ├── permission/                # 权限核心：models/policy/storage/checker/approval
│   ├── decoy_monitor/             # 诱饵生成器 + 监控器
│   ├── runtime/                   # ToolRequest/ToolInterceptor/ExecutionProxy/AgentAdapter
│   ├── audit_logger/              # 审计日志与报告
│   └── ui/                        # Streamlit 管理后台
├── openclaw_plugin/govagent-shield/
│   ├── index.ts                   # 插件入口：definePluginEntry
│   ├── src/decision.ts            # Decision Contract（唯一 action 枚举）
│   ├── src/hooks.ts               # before/after_tool_call Decision Executor
│   ├── src/http_client.ts         # HTTP + schema 校验（不解释策略）
│   └── src/tool_request.ts        # OpenClaw 上下文 → ToolRequest
├── openclaw_adapter/              # DEPRECATED：旧适配器，仅兼容保留
├── samples/                       # 攻击样本库 + 正常任务样本
├── tests/                         # pytest + 契约测试（decision_contract.test.ts）
└── data/                          # permissions.json + decoys 诱饵资源
```

---

## 2. 当前完整执行链路

### 2.1 项目内 Agent 链路（mock/planner 模式）

```
用户输入
  ↓
GovAgent.run()
  ↓
SecurityOrchestrator.check_input()      # 输入检测 + 数据外泄三元组
  ↓  has_high_severity_match() 命中 → block 直接返回
AgentPlanner.plan() / MockReasoningEngine # 生成 ToolCall
  ↓
ToolInterceptor.intercept(ToolRequest)
  ↓
SecurityOrchestrator.check_tool_call()
  ├── ParameterChecker → r_tool
  ├── BehaviorAnalyzer.record_call + analyze → behavior_score
  ├── DecoyManager.check_access → r_decoy
  ├── PermissionChecker.check → allow/block/review
  ├── _calculate_final_risk(R_input/R_tool/R_output/R_behavior/R_decoy)
  └── DispositionEngine.decide(risk, decoy_context) → action
  ↓
allow/warn → ExecutionProxy.execute()
review/block/kill → 阻断并返回安全结果
  ↓
SecurityLogger.log_check()              # SQLite 审计
```

### 2.2 真实 OpenClaw 链路（插件）

```
OpenClaw Agent 生成 ToolCall
  ↓
plugin before_tool_call hook
  ↓
GovAgent-Shield Hook Executor
  ↓
ShieldHttpClient → POST /security/check_tool
  ↓
SecurityOrchestrator.check_tool_call()（同上完整安全链路）
  ↓
decision: allow/warn/review/block/kill
  ↓
hooks.ts：allow/warn → undefined；review → requireApproval；
         block → block:true；kill → block:true + terminate:true
  ↓
OpenClaw 继续执行或阻断工具
  ↓
after_tool_call hook → 记录执行结果（OutputGuard 接入点预留）
```

---

## 3. 已实现安全模块分析

### 3.1 输入检测 / Prompt 分析

- 文件：`src/input_guard/detector.py`、`rules.py`、`sensitive_data_leak_detector.py`
- 功能：越狱（ignore/act as/DAN/中文角色覆盖）、指令覆盖、敏感读取/外传、数据外泄三元组（敏感词+外发+外部目标）
- 接入：`orchestrator.check_input()`，`GovAgent.run()` 前置高危阻断
- 输入/输出：`scan(text)` → `{risk_score, risk_level, findings, is_attack}`；`check_input()` → `{passed, action, reason, findings}`

### 3.2 ParameterChecker

- 文件：`src/security/parameter_checker.py`
- 检查：read_document 路径穿越/敏感关键词；query_citizen_info 批量/完整身份证；upload_data 外部目标
- 是否参与风险：是，`r_tool = base_risk + param_risk`
- 输入/输出：`check(tool_name, params)` → `{risk_score(增量), findings}`

### 3.3 BehaviorAnalyzer

- 文件：`src/security/behavior_analyzer.py`
- 单步行为：高频文件访问、批量查询（≥5 次）
- 行为链：read→upload（含敏感词加权）、危险工具组合（query/read + upload）
- 输出：`behavior_score`，进入最终风险计算

### 3.4 PermissionChecker

- 文件：`src/security/permission_checker.py`（包装 `src/permission/checker.py`）
- 定位：当前是「权限管理 + 前置决策」：single_user 未注册 agent 全放行，enterprise 未注册拦截；命中 restricted → block，require_approval → review
- 注意：权限层 block/review 会绕过 RiskScorer 直接返回；权限放行后才进入风险评分

### 3.5 RiskScorer

- 文件：`src/risk_engine/scorer.py` + `orchestrator._calculate_final_risk()`
- 规则：五维加权 `0.15/0.25/0.15/0.15/0.30`，`Final = max(weighted, max_dim * 0.85)`
- 输入：R_input、R_tool、R_output、R_behavior、R_decoy
- 阈值：MEDIUM 0.30 / HIGH 0.50 / VERY_HIGH 0.70 / CRITICAL 0.85

### 3.6 DispositionEngine

- 文件：`src/risk_engine/actions.py`
- 决策：allow / warn / review / block / kill
- 附加：DecoyTriggered 策略（authorized→review，upload→kill，否则 block）

---

## 4. 当前 Demo 能力

### 已有能力

- Prompt Injection / 越狱 / 指令覆盖（输入规则 + 前置阻断）
- 数据外泄（输入三元组、输出脱敏、行为链）
- 文件操作风险（参数路径穿越/敏感词）
- 工具调用拦截（ToolInterceptor + OpenClaw before_tool_call）
- 动态诱饵（DecoyManager，政企诱饵资源）
- 权限控制（single_user / enterprise 双模式）
- 行为链熔断（kill）
- 审计（SecurityLogger SQLite + audit_logger + 管理后台）
- Decision Contract（统一 action 枚举，跨 Python/TS 对齐）

### 缺失能力

- 知识库污染 / 网页内容注入检测（仅检测用户输入，未检测文档内容）
- 数据分级（公开/内部/敏感/核心）作为风险输入
- 政企 IAM/RBAC/ABAC 真实策略接口（目前是 JSON 静态策略）
- 人工审批流端到端（OpenClaw requireApproval 已接线，管理后台审批待闭环）
- 真实 LLM 全链路验证（当前 mock planner）
- after_tool_call 输出脱敏接入（OutputGuard 已实现，未在 OpenClaw 侧启用）
- Decoy/Honey Token 按需触发（当前 setup 即生成）

---

## 5. 重点问题回答

### 5.1 Policy Adapter（模拟政企 IAM/RBAC/ABAC）

- 挂载点：`PermissionChecker` 的策略解析层，即 `src/permission/storage.py` 与 `checker.py` 之间。
- 建议：新增策略提供者接口（`policy_source`），Adapter 实现该接口返回 `PermissionPolicy`；不改 checker 主流程，只替换策略来源。
- 是否修改 PermissionChecker：核心签名不变，仅构造时注入 adapter；权限结果仍走现有 allow/block/review。

### 5.2 Data Classification（公开/内部/敏感/核心）

- 接入点：`orchestrator.check_tool_call()` 中构造最终风险前。
- 建议：新增分类器对 `tool_name + params` 分类，输出 `data_class` + 等级分；作为 R_tool 的附加维度或独立 `R_data` 传入 `_calculate_final_risk()`。
- 优点：不替换 Runtime Defense，只增强评分输入。

### 5.3 Input Risk Analyzer（用户输入/知识库污染/网页内容）

- 接入点：`orchestrator.check_input()`（风险上下文）与工具输出回写。
- 建议：作为「风险上下文」注入，只提高 R_input / 记录 findings，不直接阻断；明确高危再由现有 DispositionEngine 决策。
- 网页/知识库内容：在 `check_tool_call` 对文档读取结果做二次扫描（OutputGuard/内容注入检测），仍由同一链路评分。

### 5.4 Audit Logger

- 最佳插入点：`orchestrator.check_tool_call()` 末尾（已有 `SecurityLogger.log_check`）。
- 补充：将 `policy_id`、`decision_reason`、`defense_stage` 写入 details；OpenClaw 侧 `after_tool_call` 记录执行结果与脱敏。

### 5.5 Decoy / Honey Token

- 触发阶段：`DecoyManager.check_access()`（已有），但应改为「按需触发」：
  - 仅当 Agent 实际访问路径/资源命中诱饵注册表时产生信号；
  - 不默认对每个 ToolCall 全量扫描；
  - 命中后作为 R_decoy 进入 RiskScorer，不直接 kill（保留 DispositionEngine 决策权）。

---

## 6. 最小修改方案（建议，未执行）

### 新增文件

- `src/security/policy_adapter.py`：IAM/RBAC/ABAC 策略源接口 + 默认 JSON 实现
- `src/security/data_classifier.py`：公开/内部/敏感/核心分级器
- `src/input_guard/input_risk_analyzer.py`：用户输入/文档内容风险上下文分析器
- `tests/test_policy_adapter.py`、`tests/test_data_classifier.py`、`tests/test_input_risk_analyzer.py`

### 修改文件（兼容式，仅扩展输入）

- `src/security/orchestrator.py`：注入分类器/分析器，扩展 `_calculate_final_risk()` 输入
- `src/risk_engine/scorer.py`：支持 `R_data` 维度（可选，向后兼容）
- `src/security/decoy_manager.py`：check_access 改为显式按需调用
- `src/security/security_logger.py`：审计字段增加 `policy_id`（可选列，兼容）
- `src/main.py`：接口透传新增字段（可选）

### 删除文件

- 无

### 风险与影响

- 全部为新增输入源 + 兼容扩展，不改变现有 action 语义与测试期望
- 数据分级若作为新权重加入，需同步更新红队 ASR 基线验证

---

## 7. 推荐 Demo 设计

1. **正常办公**：会议纪要读取 → allow
2. **内部资料提醒**：经营分析报告读取 → warn
3. **凭证暴露**：服务配置读取 → block（内容触发）
4. **文档隐藏指令**：知识库指南附录注入 → block
5. **客户数据外发**：客户名单 + 外发请求 → review/block
6. **行为链攻击**：连续读取配置+客户资料+导出 → kill
7. **数据分级演示**：同一文件在公开/内部目录的评分差异
8. **策略适配演示**：enterprise 模式未注册 agent → block
9. **审计溯源演示**：管理后台展示 policy_id / defense_stage / decision
10. **审批流演示**：review 决策进入 requireApproval

---

## 8. 结论

当前架构已形成「输入检测 → 工具参数 → 行为链 → 诱饵 → 权限 → 风险评分 → 处置 → 审计」的完整闭环，并以 Decision Contract 统一 Python 决策端与 OpenClaw Runtime 执行端。后续增强应沿「新增风险输入源 + 保持 DispositionEngine 唯一决策」方向扩展，避免在 Node 侧重复判断策略。
