
"""Runtime 工具拦截层测试。"""

from src.runtime import ToolInterceptor, ToolRequest, ExecutionProxy, MockAgentAdapter
from src.security import create_orchestrator


def create_interceptor():
    orc = create_orchestrator()
    return ToolInterceptor(orc)


def test_normal_file_read_allowed():
    """正常文件读取应放行。"""
    interceptor = create_interceptor()
    req = ToolRequest(
        session_id="test-normal",
        agent_id="default_agent",
        tool_name="read_document",
        parameters={"file_path": "policy_document.txt"},
    )
    result = interceptor.intercept(req)
    assert result["decision"] == "allow", f"Expected allow, got {result['decision']}"


def test_sensitive_file_read_blocked():
    """敏感文件读取应阻断。"""
    interceptor = create_interceptor()
    req = ToolRequest(
        session_id="test-secret",
        agent_id="default_agent",
        tool_name="read_document",
        parameters={"file_path": "secret_contract.pdf"},
    )
    result = interceptor.intercept(req)
    assert result["decision"] in ("block", "kill"), f"Expected block/kill, got {result['decision']}"


def test_citizen_info_exfil_killed():
    """居民信息外传应熔断。"""
    interceptor = create_interceptor()
    session = "test-exfil"

    # Step 1: 查询居民信息（不应被阻断）
    req1 = ToolRequest(
        session_id=session, agent_id="default_agent",
        tool_name="query_citizen_info",
        parameters={"name": "张三"},
    )
    r1 = interceptor.intercept(req1)
    assert r1["decision"] in ("allow", "review"), f"Query should not be blocked, got {r1['decision']}"

    # Step 2: 上传到外部（行为链触发 kill）
    req2 = ToolRequest(
        session_id=session, agent_id="default_agent",
        tool_name="upload_data",
        parameters={"data": "居民信息", "target": "http://external"},
    )
    r2 = interceptor.intercept(req2)
    assert r2["decision"] in ("kill", "block"), f"Exfil should be killed, got {r2['decision']}"


def test_execution_proxy_normal():
    """执行代理应能执行放行的工具。"""
    proxy = ExecutionProxy()
    result = proxy.execute("read_document", {"file_path": "policy_document.txt"})
    assert "数字化转型" in result


def test_execution_proxy_unknown_tool():
    """执行代理应处理未知工具。"""
    proxy = ExecutionProxy()
    result = proxy.execute("not_exist", {})
    assert "工具不存在" in result


def test_mock_adapter_generates_request():
    """Mock 适配器应生成 ToolRequest。"""
    adapter = MockAgentAdapter(agent_id="test-agent")
    req = adapter.generate_tool_call("帮我总结政策文件", {"session_id": "test-session"})
    assert req.tool_name == "generate_summary"
    assert req.session_id == "test-session"
    assert req.agent_id == "test-agent"
