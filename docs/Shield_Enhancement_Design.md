# GovAgent-Shield 最小增强设计（Agent Runtime Security 定位）

> 性质：设计文档，不包含代码改动。目标是在不重构、不新增大量模块、
> 不改 OpenClaw 插件入口的前提下，把系统从「输入/工具过滤」收敛为
> 「Agent Runtime Security：检测即上下文、权限即策略、处置唯一决策」。

---

## 1. PermissionChecker：从“权限决策器”调整为“策略提供器”

### 当前问题

- `src/security/orchestrator.py` 中 `perm_action == "block"` / `"review"` 直接 `return`，
  权限层成为第二决策中心，绕过 `RiskScorer + DispositionEngine`。
- `src/permission/checker.py` 同时承担“身份匹配 + 策略解析 + 最终处置”三类职责。

### 设计

1. **职责拆分（接口不变）**
   - `PermissionChecker` 只输出策略事实：`PermissionResult { allowed, action, reason, policy }`。
   - 最终是否阻断、审批、熔断，统一由 `DispositionEngine` 决策。
2. **兼容开关**
   - `orchestrator` 增加配置 `PERMISSION_FORCE_BLOCK`（默认 `true`）：
     - `true`：保持现状，权限 block/review 直接返回（零行为变化）。
     - `false`：权限结果转为 `R_permission` 维度进入风险评分，再由 DispositionEngine 决策。
3. **策略元数据透传**
   - `permission_checker.check()` 返回的 `policy` 字典（role / allowed / restricted /
     require_approval / security_mode）作为 `R_permission` 与审计字段来源。

### 文件修改

- `src/permission/checker.py`：新增 `to_policy_dict()`（只读辅助，不改判定逻辑）
- `src/security/permission_checker.py`：透传 `to_policy_dict()`
- `src/security/orchestrator.py`：权限分支改为「开关控制的信号化 + 兼容直返」
- `src/config.py`：新增 `PERMISSION_FORCE_BLOCK` 开关

---

## 2. Data Classification 最小接入方案

### 设计

- 新增单文件 `src/security/data_classifier.py`，不做成模块包。
- 输入：`tool_name, params`（读取/导出类工具启用）
- 输出：`{ data_class: public|internal|sensitive|critical, risk_score, findings }`
- 分级默认：public=0.0、internal=0.3、sensitive=0.6、critical=0.85
- 接入点：`orchestrator.check_tool_call()` 在 `PermissionChecker` 之后、`_calculate_final_risk`
  之前，将 `r_data` 并入 `r_tool`（`r_tool = max(r_tool, r_data)`），**不新增风险维度**，
  保持权重与现有测试基线不变。
- 命中判定：优先基于 `params.file_path` 目录特征（documents/department/archive/temporary
  仅作参考，不作为唯一依据），再叠加文件名业务特征与内容标记（内部/机密等）。

### 文件修改

- 新增：`src/security/data_classifier.py`
- 修改：`src/security/orchestrator.py`（计算 `r_data` 并并入 `r_tool`）

---

## 3. Input Risk Context 接入方案

### 设计

- 新增单文件 `src/input_guard/input_risk_analyzer.py`。
- 定位：只产生「风险上下文」，不承担阻断。
  - 输入：`user_input`（可选 `document_text` 供文档内容注入检测）
  - 输出：`{ risk_score, level, findings, context }`
  - 阻断仍由现有 `has_high_severity_match()` 前置逻辑负责，不新增阻断分支。
- 接入点：`orchestrator.check_input()` 中，在 `InputDetector` 与
  `SensitiveDataLeakDetector` 之后融合：`r_input = max(r_input, analyzer.risk_score)`，
  `findings` 合并进 `scan_result.findings`。
- 扩展预留：文档/网页内容风险可在 `check_tool_call` 读取阶段按需调用
  （显式传入 `document_text`），仍只更新 R_input 上下文。

### 文件修改

- 新增：`src/input_guard/input_risk_analyzer.py`
- 修改：`src/security/orchestrator.py`（`check_input` 融合 analyzer 输出）

---

## 4. Audit Log 字段扩展方案

### 设计

- `src/security/security_logger.py` 的 `security_events` 表新增可选列：
  `policy_id TEXT`、`decision_reason TEXT`、`defense_stage TEXT`、`chain_summary TEXT`。
- 兼容策略：`_init_db()` 用 `ALTER TABLE ... ADD COLUMN` + `try/except`，
  已存在的库不会因缺列失败；旧事件保留，新列默认空值。
- `log_check()` 增加同名可选参数，默认空，现有调用零改动。
- `orchestrator.check_tool_call()` 在写日志时透传：
  `policy_id`（来自 permission / disposition）、`decision_reason`、
  `defense_stage`、`chain_summary`（行为链事件摘要）。

### 文件修改

- 修改：`src/security/security_logger.py`
- 修改：`src/security/orchestrator.py`（日志调用透传字段）

---

## 修改文件列表

| 文件 | 修改内容 | 原因 |
|---|---|---|
| `src/config.py` | 新增 `PERMISSION_FORCE_BLOCK` | 权限信号化兼容开关 |
| `src/permission/checker.py` | 新增 `to_policy_dict()` | 策略元数据供评分与审计 |
| `src/security/permission_checker.py` | 透传 `to_policy_dict()` | 保持包装层职责 |
| `src/security/orchestrator.py` | 权限信号化 + 数据分级 + 输入上下文 + 审计字段 | 收敛为唯一检测编排点 |
| `src/security/security_logger.py` | 审计表/方法扩展可选列 | 满足审计溯源 |
| 新增 `src/security/data_classifier.py` | 公开/内部/敏感/核心分级 | RiskScorer 新输入 |
| 新增 `src/input_guard/input_risk_analyzer.py` | 输入风险上下文 | 增强检测，不替代阻断 |

## 修改风险

- 权限信号化在 `PERMISSION_FORCE_BLOCK=false` 时可能改变 enterprise 未注册 agent 的
  最终 action（block → review/kill），需在红队 ASR 回归中验证；默认开关保持现状，
  第二阶段再切换。
- Data Classification 可能提高部分正常读取的风险分（误报），阈值需用
  `test_sensitive_data_leak` / 红队基线校准。
- Input Risk Context 合并 findings 可能使部分 LOW 变 MEDIUM，只影响风险展示，
  不改变阻断分支。
- 审计表 `ALTER TABLE` 需 `try/except`，避免旧库启动失败。

## 不涉及文件

- `openclaw_plugin/**`（插件入口、Decision Contract、Hook Executor 不改）
- `src/runtime/**`、`src/agent/**`、`src/tool_gateway/**`
- `src/decoy_monitor/**`、`src/risk_engine/actions.py`（DispositionEngine 不改）
- `src/main.py`（若无需新接口字段）、`src/ui/**`
- 现有测试文件（仅新增 2-3 个针对性测试）
