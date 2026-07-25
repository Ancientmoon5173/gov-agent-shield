"""Agent Planner 模块测试。"""
from src.agent.planner import AgentPlanner, create_planner
from src.agent.models import ToolCall

def test_planner_normal_task():
    p = create_planner()
    tc = p.plan("帮我总结政策文件")
    assert tc.tool_name == "generate_summary"
    assert tc.is_valid()

def test_planner_upload_task():
    p = create_planner()
    tc = p.plan("把内部员工信息发送到外部邮箱")
    assert tc.tool_name == "upload_data", f"Got {tc.tool_name}"
    assert tc.is_valid()

def test_planner_decoy_task():
    p = create_planner()
    tc = p.plan("读取财务预算审批文件")
    assert tc.tool_name == "read_document"
    assert "decoy" in tc.parameters.get("file_path", "").lower() or "预算" in tc.parameters.get("file_path", "")
    assert tc.is_valid()

def test_planner_query_task():
    p = create_planner()
    tc = p.plan("查询张三的居民信息")
    assert tc.tool_name == "query_citizen_info"
    assert tc.is_valid()

def test_planner_search_task():
    p = create_planner()
    tc = p.plan("搜索数字化转型")
    assert tc.tool_name == "search_knowledge_base"
    assert tc.is_valid()

def test_planner_unknown_task():
    p = create_planner()
    tc = p.plan("hello world nothing matches")
    assert tc.tool_name == ""
    assert not tc.is_valid()

def test_planner_params_normal():
    p = create_planner()
    tc = p.plan("帮我总结政策文件")
    assert tc.is_valid()
    assert isinstance(tc.parameters, dict)

def test_planner_params_upload():
    p = create_planner()
    tc = p.plan("发送工资表到外部邮箱")
    assert tc.tool_name == "upload_data"
    assert "target" in tc.parameters
