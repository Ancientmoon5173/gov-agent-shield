"""
GovAgent - 政企场景 AI Agent 核心。

这是整个系统的"大脑"——接收用户请求，决定调用哪个工具，
整合工具结果后回复用户。

关键设计点：
1. 支持 Mock 模式（无 API 也可运行）和 Real 模式（连接真实 LLM）
2. 在工具执行前后预留安全层钩子
3. 记录完整的调用链供审计使用
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from src.config import LLM_MOCK_MODE, LLM_API_KEY, LLM_API_BASE, LLM_MODEL_NAME
from src.security import create_orchestrator
from src.agent.tools import GOV_TOOLS, TOOL_METADATA
from src.agent.prompts import SYSTEM_PROMPT
from .planner import create_planner


# ========================
# Mock 模式下的 LLM 模拟器
# ========================
class MockReasoningEngine:
    """
    模拟 LLM 的推理过程。

    在 Mock 模式下，我们不依赖外部 LLM API，而是使用规则引擎
    模拟 ReAct 流程的思考（Thought）、行动（Action）、观察（Observation）步骤。

    这是为了让开发过程不依赖 API 也能测试完整流程。
    """

    # 工具名称 → 触发关键词映射
    TRIGGER_MAP = {
        "read_document": [
            "读取", "阅读", "打开文件", "查看文件", "政策文件",
            "read", "document", "file", "政策", "方案", "通知",
        ],
        "search_knowledge_base": [
            "搜索", "查找", "查询知识", "找一下", "搜一下",
            "search", "find", "知识库", "办事指南",
        ],
        "query_citizen_info": [
            "查询居民", "查人", "居民信息", "个人信息","信息"
            "citizen", "居民", "身份证", "社保",
        ],
        "generate_summary": [
            "总结", "摘要", "概括", "提炼", "归纳",
            "summary", "summarize", "简述",
        ],
    }

    def __init__(self):
        self.conversation_history: List[Dict] = []

    def analyze_intent(self, user_input: str) -> Dict[str, Any]:
        """
        分析用户输入的意图，返回最匹配的工具和参数。

        返回格式：
        {
            "thought": "推理过程",
            "tool": "工具名称",
            "params": {"参数名": "参数值"},
            "confidence": 0.0-1.0,
        }
        """
        user_input_lower = user_input.lower()
        matched_tools = []

        # 步骤1：找出所有匹配的工具
        for tool_name, keywords in self.TRIGGER_MAP.items():
            score = 0
            matched_kws = []
            for kw in keywords:
                if kw.lower() in user_input_lower:
                    score += 0.2
                    matched_kws.append(kw)
            if score > 0:
                matched_tools.append((tool_name, score, matched_kws))

        # 步骤2：选择匹配度最高的工具
        if not matched_tools:
            return {
                "thought": "用户输入没有明确匹配到已注册的工具，尝试直接回答。",
                "tool": None,
                "params": {},
                "confidence": 0.0,
            }

        matched_tools.sort(key=lambda x: x[1], reverse=True)
        best_tool = matched_tools[0]
        tool_name = best_tool[0]
        matched_kws = best_tool[2]

        # 步骤3：提取参数
        params = self._extract_params(tool_name, user_input)

        thought = (
            "用户输入包含关键词 " + ", ".join(matched_kws) + "，"
            "判断需要使用 " + tool_name + " 工具。"
        )

        return {
            "thought": thought,
            "tool": tool_name,
            "params": params,
            "confidence": min(best_tool[1], 1.0),
        }

    def _extract_params(self, tool_name: str, user_input: str) -> Dict[str, str]:
        """根据工具类型提取参数。"""
        if tool_name == "read_document":
            # 尝试从输入中提取文件名
            for fname in ["policy_document.txt", "employee_info.txt", "citizen_data.txt"]:
                if fname in user_input or fname.replace(".txt", "") in user_input:
                    return {"file_path": fname}
            return {"file_path": "policy_document.txt"}

        elif tool_name == "search_knowledge_base":
            # 提取搜索关键词
            import re
            # 尝试匹配引号内的内容
            quoted = re.findall(r'[""](.+?)[""]', user_input)
            if quoted:
                return {"query": quoted[0]}
            # 去掉常见前缀词
            search_terms = user_input
            for prefix in ["搜索", "查找", "搜一下", "找一下", "search for", "find"]:
                search_terms = search_terms.replace(prefix, "")
            return {"query": search_terms.strip()[:50]}

        elif tool_name == "query_citizen_info":
            # 尝试提取姓名和身份证号
            name = ""
            id_number = ""
            # 简单姓名提取
            for candidate in ["张三", "李四", "王五", "赵六", "陈七"]:
                if candidate in user_input:
                    name = candidate
                    break
            return {"name": name, "id_number": id_number}

        elif tool_name == "generate_summary":
            return {"content": user_input, "max_length": 200}

        return {}


# ========================
# GovAgent 主类
# ========================
class GovAgent:
    """
    政企场景 AI Agent。

    使用方式：
        agent = GovAgent(mode="mock")  # 开发模式
        result = agent.run("帮我总结政策文件")

        agent = GovAgent(mode="real")  # 连接真实 LLM
        result = agent.run("帮我查一下张三的居民信息")
    """

    def __init__(
        self,
        mode: str = "mock",
        security_hooks: Optional[Dict[str, Callable]] = None,
    ):
        """
        Args:
            mode: "mock"（模拟模式，无API）或 "real"（真实LLM模式）
            security_hooks: 安全层钩子函数（将在阶段3注入）
        """
        self.mode = mode
        self.tools = GOV_TOOLS
        self.tool_map = {t.name: t for t in self.tools}
        self.metadata = TOOL_METADATA

        # 🔒 安全层钩子（现在为空，阶段3会实现）
        self.security_hooks = security_hooks or {
            "pre_tool_call": None,   # 工具调用前检查
            "post_tool_call": None,  # 工具调用后检查
            "pre_input": None,       # 用户输入检查
            "post_output": None,     # 输出检查
        }

        # 安全协调器（阶段3）
        self.orchestrator = create_orchestrator()

        # 推理引擎
        self.reasoning = MockReasoningEngine() if mode == "mock" else None
        self.planner = create_planner()

        # 激活安全层钩子
        self._activate_security_hooks()

        # LangChain Agent（real模式使用）
        self._agent_executor = None
        if mode == "real":
            self._init_langchain_agent()

        # 会话管理
        self.sessions: Dict[str, List[Dict]] = {}

    def _init_langchain_agent(self) -> None:
        """初始化 LangChain ReAct Agent（real 模式）。"""
        llm = ChatOpenAI(
            model=LLM_MODEL_NAME,
            api_key=LLM_API_KEY,
            base_url=LLM_API_BASE,
            temperature=0.1,
        )

        prompt = PromptTemplate.from_template(SYSTEM_PROMPT)
        agent = create_react_agent(llm, self.tools, prompt)

        self._agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
        )

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行一次 Agent 任务。

        Args:
            user_input: 用户输入
            session_id: 会话ID（不传会自动生成）

        Returns:
            {
                "session_id": str,       # 会话ID
                "user_input": str,       # 用户输入
                "agent_response": str,   # Agent 回复
                "trace": [dict],         # 调用链（工具调用记录）
                "risk_assessment": dict, # 🔒 安全评估（阶段3实现）
            }
        """
        if not session_id:
            session_id = str(uuid.uuid4())

        # 初始化会话记录
        if session_id not in self.sessions:
            self.sessions[session_id] = []

        trace = []

        # 🔒 阶段3：这里会插入 pre_input 安全检查
        # if self.security_hooks["pre_input"]:
        #     result = self.security_hooks["pre_input"](user_input)
        #     if result["blocked"]:
        #         return {"blocked": True, ...}

        # 存储当前会话信息（供安全钩子使用）
        self._current_session = session_id
        self._current_input = user_input

        if self.mode == "planner":
            result = self._planner_execute(user_input, session_id, trace)
        elif self.mode == "mock":
            result = self._mock_execute(user_input, session_id, trace)
        else:
            result = self._real_execute(user_input, session_id, trace)

        # 保存会话历史
        self.sessions[session_id].append({
            "user": user_input,
            "agent": result.get("agent_response", ""),
            "trace": trace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 执行安全检查（输入 + 输出）
        input_check = self.orchestrator.check_input(session_id, user_input)

        return {
            "session_id": session_id,
            "user_input": user_input,
            "agent_response": result.get("agent_response", ""),
            "trace": trace,
            "tool_call": result.get("tool_call", {}),
            "security_result": result.get("security_result", {}),
            "risk_assessment": {
                "input_check": {
                    "risk_score": input_check["risk_score"],
                    "risk_level": input_check["risk_level"],
                    "action": input_check["action"],
                    "findings": input_check["findings"],
                },
                "summary": f"输入检测: {input_check['action']} | 评分: {input_check['risk_score']}",
            },
        }

    def _mock_execute(
        self,
        user_input: str,
        session_id: str,
        trace: List[Dict],
    ) -> Dict[str, str]:
        """
        Mock 模式执行流程。

        模拟 ReAct 的 Thought → Action → Observation 循环。
        """
        # 步骤1：分析意图（模拟 Thought）
        intent = self.reasoning.analyze_intent(user_input)
        trace.append({
            "step": "thought",
            "content": intent["thought"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 如果没有匹配到工具，直接回复
        if intent["tool"] is None:
            response = (
                f"您好，我是政务智能助手。我可以帮您：\n"
                f"1. 读取政府文档（如政策文件）\n"
                f"2. 搜索知识库信息\n"
                f"3. 查询居民登记信息\n"
                f"4. 生成内容摘要\n\n"
                f"请告诉我您需要什么帮助？"
            )
            return {"agent_response": response}

        # 步骤2：执行工具调用（模拟 Action）
        tool_name = intent["tool"]
        params = intent["params"]

        trace.append({
            "step": "action",
            "tool": tool_name,
            "params": params,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 🔒 安全检测：pre_tool_call
        if self.security_hooks["pre_tool_call"]:
            check = self.security_hooks["pre_tool_call"](tool_name, params)
            trace.append({
                "step": "security_check",
                "result": check,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if check["blocked"] or check["action"] == "kill":
                action_name = check.get("action_name", "阻断")
                reason = check.get("reason", "操作已被安全系统阻断")
                return {"agent_response": f"🔒 安全系统{action_name}：{reason}"}

        # 步骤3：执行工具（模拟 Observation）
        try:
            tool_func = self.tool_map[tool_name]
            observation = tool_func.invoke(params)
        except Exception as e:
            observation = f"工具执行出错：{str(e)}"

        trace.append({
            "step": "observation",
            "result": observation[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 🔒 安全检测：post_tool_call
        if self.security_hooks["post_tool_call"]:
            check = self.security_hooks["post_tool_call"](tool_name, observation)
            if check["has_sensitive_data"]:
                trace.append({
                    "step": "output_sanitized",
                    "sensitive_types": [f["label"] for f in check["findings"]],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                observation = check["masked_output"]

        # 步骤4：生成回复（模拟 Final Answer）
        response = self._format_response(tool_name, params, observation)
        return {"agent_response": response}

    def _real_execute(
        self,
        user_input: str,
        session_id: str,
        trace: List[Dict],
    ) -> Dict[str, str]:
        """
        Real 模式执行流程。

        使用 LangChain AgentExecutor 调用真实 LLM。
        """
        if not self._agent_executor:
            return {"agent_response": "错误：Agent 未正确初始化，请检查 API 配置"}

        try:
            result = self._agent_executor.invoke({
                "input": user_input,
            })
            return {"agent_response": result.get("output", "执行完成")}
        except Exception as e:
            return {"agent_response": f"执行出错：{str(e)}"}

    def _planner_execute(self, user_input, session_id, trace):
        """
        Planner 模式执行流程。

        输入 -> AgentPlanner.plan() -> ToolCall -> SecurityOrchestrator -> 结果
        模拟真实 LLM Agent 的意图理解、工具选择和参数生成过程。
        """
        tool_call = self.planner.plan(user_input)
        trace.append({"step": "planning", "tool": tool_call.tool_name, "params": tool_call.parameters, "reasoning": tool_call.reasoning, "timestamp": datetime.now(timezone.utc).isoformat()})

        result = {"agent_response": "", "tool_call": tool_call.to_dict(), "security_result": {}}

        if not tool_call.is_valid():
            result["agent_response"] = "未能理解您的请求，请尝试重新描述。"
            return result

        # Security check
        if self.security_hooks["pre_tool_call"]:
            check = self.security_hooks["pre_tool_call"](tool_call.tool_name, tool_call.parameters)
            trace.append({"step": "security_check", "result": check, "timestamp": datetime.now(timezone.utc).isoformat()})
            result["security_result"] = check
            if check["blocked"] or check["action"] == "kill":
                result["agent_response"] = "🔒 " + "安全系统" + check.get("action_name", "阻断") + "：" + check.get("reason", "")
                return result

        # Execute tool
        try:
            observation = self.tool_map[tool_call.tool_name].invoke(tool_call.parameters)
        except Exception as e:
            observation = f"执行异常: {str(e)}"

        trace.append({"step": "observation", "result": observation[:200], "timestamp": datetime.now(timezone.utc).isoformat()})

        # Output check
        if self.security_hooks["post_tool_call"]:
            check = self.security_hooks["post_tool_call"](tool_call.tool_name, observation)
            if check.get("has_sensitive_data"):
                observation = check["masked_output"]
                trace.append({"step": "output_sanitized", "sensitive_types": [f["label"] for f in check["findings"]], "timestamp": datetime.now(timezone.utc).isoformat()})

        result["agent_response"] = self._format_response(tool_call.tool_name, tool_call.parameters, observation)
        return result


    def _format_response(self, tool_name: str, params: Dict, observation: str) -> str:
        """格式化工具执行结果为用户可读的回复。"""
        metadata = self.metadata.get(tool_name, {})
        display_name = metadata.get("display_name", tool_name)

        lines = [
            f"✅ 已完成「{display_name}」操作\n",
        ]

        # 添加参数说明
        if params:
            param_desc = "、".join(f"{k}={v}" for k, v in params.items() if v)
            if param_desc:
                lines.append(f"📌 查询条件：{param_desc}\n")

        # 添加结果
        lines.append(f"📋 结果：\n{observation}")

        return "\n".join(lines)

    def get_session_history(self, session_id: str) -> List[Dict]:
        """获取指定会话的历史记录。"""
        return self.sessions.get(session_id, [])

    def get_available_tools(self) -> List[Dict]:
        """获取可用工具列表（含元数据）。"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "args": t.args,
                "metadata": self.metadata.get(t.name, {}),
            }
            for t in self.tools
        ]

    def inject_security_hook(self, hook_type: str, hook_func: Callable) -> None:
        """
        注入安全层钩子函数。

        在阶段3，安全模块会调用此方法注册自己的检查函数。

        Args:
            hook_type: 钩子类型（pre_tool_call / post_tool_call / pre_input / post_output）
            hook_func: 钩子函数
        """
        if hook_type in self.security_hooks:
            self.security_hooks[hook_type] = hook_func
            print(f"[GovAgent] 安全钩子已注册: {hook_type}")
        else:
            raise ValueError(f"未知的钩子类型: {hook_type}")


# ========================
# 便捷函数
# ========================
    def _activate_security_hooks(self) -> None:
        """激活安全层钩子，将安全检查注入 Agent 调用链路。"""
        def pre_tool_hook(tool_name, params):
            session_id = getattr(self, "_current_session", "unknown")
            user_input = getattr(self, "_current_input", "")
            result = self.orchestrator.check_tool_call(session_id, tool_name, params, user_input)
            return result

        def pre_input_hook(user_input):
            session_id = getattr(self, "_current_session", "unknown")
            result = self.orchestrator.check_input(session_id, user_input)
            return result

        def post_tool_hook(tool_name, observation):
            session_id = getattr(self, "_current_session", "unknown")
            result = self.orchestrator.check_output(session_id, tool_name, observation)
            return result

        self.inject_security_hook("pre_tool_call", pre_tool_hook)
        self.inject_security_hook("pre_input", pre_input_hook)
        self.inject_security_hook("post_tool_call", post_tool_hook)
def create_gov_agent(mode: str = "mock") -> GovAgent:
    """创建并返回一个配置好的 GovAgent 实例。"""
    return GovAgent(mode=mode)
