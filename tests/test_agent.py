"""
Agent 模块测试。

测试 GovAgent 的基本功能和工具调用链路。
"""

from src.agent import GovAgent
from src.agent.tools import GOV_TOOLS, TOOL_METADATA


def test_agent_creation():
    """测试 Agent 创建。"""
    agent = GovAgent(mode="mock")
    assert agent is not None
    assert agent.mode == "mock"
    assert len(agent.tools) == 5


def test_available_tools():
    """测试工具列表。"""
    assert len(GOV_TOOLS) == 5
    tool_names = [t.name for t in GOV_TOOLS]
    assert "read_document" in tool_names
    assert "search_knowledge_base" in tool_names
    assert "query_citizen_info" in tool_names
    assert "generate_summary" in tool_names


def test_tool_metadata():
    """测试工具元数据。"""
    assert TOOL_METADATA["read_document"]["risk_level"] == "MEDIUM"
    assert TOOL_METADATA["query_citizen_info"]["risk_level"] == "HIGH"
    assert TOOL_METADATA["search_knowledge_base"]["risk_level"] == "LOW"


def test_mock_agent_run():
    """测试 Mock 模式下 Agent 执行任务。"""
    agent = GovAgent(mode="mock")
    result = agent.run("帮我总结一下政策文件")
    assert result["user_input"] == "帮我总结一下政策文件"
    assert len(result["agent_response"]) > 0
    assert len(result["trace"]) > 0
    assert result["session_id"] is not None


def test_mock_agent_trace():
    """测试 Agent 执行链路追踪。"""
    agent = GovAgent(mode="mock")
    result = agent.run("查询张三的居民信息")

    # 验证调用链包含 thought、action、observation 三个步骤
    steps = [s["step"] for s in result["trace"]]
    assert "thought" in steps
    assert "action" in steps
    assert "observation" in steps

    # 验证 action 步骤包含工具名和参数
    action_step = [s for s in result["trace"] if s["step"] == "action"][0]
    assert "tool" in action_step
    assert "params" in action_step


def test_read_document_tool():
    """测试 read_document 工具的基本功能。"""
    from src.agent.tools import read_document
    result = read_document.invoke({"file_path": "policy_document.txt"})
    assert "数字化转型" in result
    assert "【XX市政府" in result


def test_query_citizen_info_tool():
    """测试 query_citizen_info 工具。"""
    from src.agent.tools import query_citizen_info
    result = query_citizen_info.invoke({"name": "张三"})
    assert "张三" in result
    # 验证身份证脱敏
    assert "********" in result


def test_search_knowledge_tool():
    """测试 search_knowledge_base 工具。"""
    from src.agent.tools import search_knowledge_base
    result = search_knowledge_base.invoke({"query": "数字化转型"})
    assert "数字化转型" in result
    assert "知识" in result


def test_agent_session():
    """测试 Agent 会话管理。"""
    agent = GovAgent(mode="mock")
    result1 = agent.run("帮我总结政策文件", session_id="test-session-1")
    result2 = agent.run("查询张三信息", session_id="test-session-1")

    history = agent.get_session_history("test-session-1")
    assert len(history) == 2
    assert history[0]["user"] == "帮我总结政策文件"
    assert history[1]["user"] == "查询张三信息"


def test_security_hook_injection():
    """测试安全层钩子注入接口。"""
    agent = GovAgent(mode="mock")

    def dummy_hook(tool_name, params):
        return {"blocked": False}

    agent.inject_security_hook("pre_tool_call", dummy_hook)
    assert agent.security_hooks["pre_tool_call"] is not None
    assert callable(agent.security_hooks["pre_tool_call"])
