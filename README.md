# gov-agent-shield
GovAgent-Shield: Depth defense framework to protect LLM Agent against prompt injection, data leakage and unauthorized access . 

# GovAgent-Shield

面向政企场景的大模型智能体安全防护平台。

## 项目定位

GovAgent-Shield 是一个轻量化的 AI Agent 安全运行时防护系统，解决政企场景下
Prompt 注入攻击、Agent 越权操作、敏感数据泄露、工具调用风险等安全问题。

## 核心功能

- **输入安全检测** — 检测 Prompt 注入、越狱攻击、指令覆盖
- **敏感数据脱敏** — 识别并脱敏姓名、手机号、身份证号等个人信息
- **工具调用安全网关** — 拦截高风险文件访问、命令执行、API 调用
- **动态诱捕与监控** — 诱饵文件/目录/Token 触碰检测
- **风险评分与处置** — 综合评分引擎，支持放行/审批/阻断/熔断
- **审计溯源** — 全链路日志、调用链重建、审计报告生成
- **可视化管理平台** — 风险看板、攻击记录、Agent 状态、安全报告

## 技术栈

- **后端**: Python + FastAPI
- **前端**: Streamlit
- **数据库**: SQLite
- **Agent 框架**: LangChain
- **安全检测**: 规则 + 轻量模型
- **部署**: Docker

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活环境并安装依赖
venv\Scripts\pip install -r requirements.txt

# 3. 启动后端
venv\Scripts\python -m src.main

# 4. 启动管理界面（另一个终端）
venv\Scripts\streamlit run src/ui/app.py
```

## 项目结构

```
GovAgent-Shield/
├── src/
│   ├── input_guard/      # 输入安全检测
│   ├── tool_gateway/     # 工具调用安全网关
│   ├── decoy_monitor/    # 动态诱捕与监控
│   ├── risk_engine/      # 风险评分与处置
│   ├── audit_logger/     # 审计日志与报告
│   └── ui/               # Streamlit 管理后台
├── samples/              # 任务样例与攻击样例
├── tests/                # 单元测试
└── docs/                 # 文档
```

## 演示场景

1. **正常政企办公助手** — 文档总结、信息查询
2. **文档中的间接注入攻击** — 隐藏恶意指令检测
3. **越权读取诱饵文件** — 诱饵触碰告警与熔断
4. **敏感信息外发脱敏** — 自动脱敏后输出
5. **审计报告生成** — 攻击链路复盘

## 许可证

本项目用于揭榜挂帅比赛，仅限学习和研究用途。



