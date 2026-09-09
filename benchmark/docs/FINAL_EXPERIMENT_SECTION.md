# 实验方案（可并入技术方案）

## 1 实验目标
验证：Agent 与 Shield 真实集成、ToolCall interception、风险识别、决策执行控制、审计链、固定危险 ToolCall 下的引擎能力。

## 2 实验分层
- Experiment A：真实 OpenClaw E2E（观察 Agent 行为 + Shield）
- Experiment B：Fixed ToolCall Engine Benchmark（控制输入，排除模型变量）
- Experiment C：No-Shield Baseline Replay（对照语义）
三者指标不得混为一个“防御率”。

## 3 数据集
100 cases：N14/S19/P26/E5/C21/A15；synthetic fixtures、无真实 PII；Ground Truth 由确定性规则生成。

## 4 指标体系
- Agent Attack Trigger Rate：危险 ToolCall 是否由 Agent 产生（A 观察；B 为固定注入不构成 generation rate）
- Shield Blocking Rate：危险 ToolCall 被 BLOCK 比例
- Conditional Blocking Rate：BLOCK / dangerous semantic calls
- Review Rate：REVIEW / dangerous semantic calls
- Residual Allow Rate：ALLOW/WARN / dangerous semantic calls
- False Positive Rate：benign 被错误 BLOCK
- Dangerous Execution Rate：仅在有真实执行证据时计算，否则 NOT MEASURED
- E2E ASR：verified dangerous execution / dangerous attempts
- Engine-E2E Consistency：match / comparable；mismatch 来源需解释

## 5 实验结果（冻结）
见 FINAL_METRICS_TABLE.md（100/100、149、104、37、8、69.8%、0、FP=2、43/66、65.15%、67/67、100% 受控、NOT MEASURED）。

## 6 结果解释
分层解释 Agent layer / Security layer / Execution layer，不合并为一个防御率。

## 7 局限性
REVIEW→Approve E2E 未闭环；No-Shield Native Agent 100-case 未执行；E 类仅 5 条；consistency 65.15%；benign FP=2；无真实外发接收器 → dangerous execution 只能报告“未观测到经验证的危险执行”。

## 8 预期效果
- 已验证：上述冻结事实。
- 预期提升（未来，非当前结果）：REVIEW approval 通道、external sink/canary receiver、更丰富 E 类、native Agent baseline、cross-model evaluation。
