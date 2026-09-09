# GovAgent-Shield

面向政企/政务场景的 **Agent Runtime Security Layer**：在真实 Agent（OpenClaw）执行工具前，通过 `before_tool_call` 完成输入/参数/数据分级/资产/行为/权限/诱饵/数据溯源的风险评估，并输出 allow / review / block / kill，同时落审计链（session→chain→call→event→escalation）。

## Overview
- 不替换 Agent，只做执行前拦截 + 决策 + 审计。
- 安全决策由独立 Python 引擎生成；OpenClaw 插件只负责拦截与执行控制。
- 全部测试数据为合成数据（SYNTH/DEMO），无真实 PII/政府数据/凭据。

## Architecture
src/security（SecurityOrchestrator 及各组件）+ src/permission + src/risk_engine + src/security/security_logger（SQLite 审计）+ FastAPI + Streamlit SOC + openclaw_plugin（Hook）。

## Key Security Pipeline
Parameter Check → Data Classification → Asset Resolution → Behavior Analysis → Data Provenance → Permission → Risk Scoring → Disposition → Audit

## Quick Start
```powershell
venv\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8000   # Shield 引擎
venv\Scripts\python -m streamlit run src/ui/app.py                        # SOC 审批/审计页
venv\Scripts\python -m pytest tests -q                                    # 核心单元测试
```
插件配置见 openclaw_plugin/govagent-shield/README.md（需本地 OpenClaw 与模型 key 方可跑真实 E2E）。

## Fixed ToolCall Benchmark（可直接复现）
```powershell
python benchmark/attack_benchmark/build_dataset.py
python benchmark/attack_benchmark/run_shield_eval.py
python benchmark/attack_benchmark/evaluate.py
python benchmark/attack_benchmark/validate_dataset.py
```
这是 Engine-level evaluation（固定 ToolCall），**不是第二次 Agent E2E**；执行类结论为 NOT MEASURED。

## Reproduction
- Engine Benchmark：脚本化、低外部依赖（见 benchmark/submission/05_reproduction/REPRODUCTION.md）。
- Real E2E：需要 OpenClaw 2026.7.2 + 模型 key + 本地引擎；复现成本与 Engine Benchmark 不同。

## Synthetic Dataset
- benchmark/attack_benchmark/fixtures 与 benchmark/fixtures：全部 synthetic；敏感级别由路径/词表触发（DataClassifier 规则）。
- attack_cases.json：100 条固定 ToolCall（N14/S19/P26/E5/C21/A15）；expected_results.json 由确定性规则生成，非 LLM。

## Example
固定工具调用示例见 benchmark/submission/03_attack_examples/examples.md；审计日志脱敏样例见 04_audit_examples/。

## Evaluation Results（冻结，数字见 benchmark/docs/FINAL_METRICS_TABLE.md）
Real E2E（真实 OpenClaw）：
- 100/100 valid；ToolCall generated=100；RUN_ENV_FAILURE=0
- 149 dangerous semantic calls：104 BLOCK / 37 REVIEW / 8 ALLOW·WARN；条件阻断率 69.8%（104/149）
- verified dangerous execution = 0（E2E ASR 0/149）
- benign FP = 2（保留限制）
- Engine↔E2E：comparable 66，一致 43（65.15%）

Fixed Benchmark（Engine-level Replay）：
- 100 个受控固定测试案例、161 次 ToolCall 中，67 个预标注危险 ToolCall 均被安全引擎判定为 BLOCK（受控阻断率 100%）
- execution = NOT MEASURED

> 限定：上述“100%”仅表示在**受控固定危险 ToolCall 输入下**的安全引擎阻断能力，不代表 Agent 整体攻击防御率；REVIEW 未闭环、No-Shield Native Agent 对照未执行等限制详见 benchmark/docs/FINAL_EVIDENCE_AUDIT_REPORT.md。
