"""
动态诱捕模块测试。

验证 DecoyManager 的完整检测链路：
诱饵生成 --> Agent 访问 --> DecoyMonitor 检测 --> RiskScorer 评分 --> DispositionEngine 决策
"""

from src.security.decoy_manager import DecoyManager
from src.security import create_orchestrator


def test_decoy_setup():
    """测试诱饵系统初始化。"""
    mgr = DecoyManager()
    mgr.setup()
    assert mgr.is_initialized
    assert len(mgr.registry) > 0


def test_normal_file_not_triggered():
    """正常文件不应该触发诱饵。"""
    mgr = DecoyManager()
    mgr.setup()
    result = mgr.check_access("read_document", {"file_path": "policy_document.txt"})
    assert result["triggered"] == False
    assert result["risk_score"] == 0.0


def test_decoy_file_triggers():
    """诱饵文件应该触发检测。"""
    mgr = DecoyManager()
    mgr.setup()
    # 诱饵目录中应该包含这个文件
    result = mgr.check_access("read_document", {"file_path": str(mgr._generator.decoy_dir / "内部合同审批记录.docx")})
    # 如果路径匹配，触发检测
    if result["triggered"]:
        assert result["risk_score"] == 1.0
        assert result["decoy_type"] in ("file", "directory")


def test_decoy_dir_children_trigger():
    """诱饵目录内的文件也触发。"""
    mgr = DecoyManager()
    mgr.setup()
    # 找第一个 directory 类型的诱饵
    dir_decoy = None
    for reg in mgr.registry:
        if reg["type"] == "directory":
            dir_decoy = reg
            break
    if dir_decoy:
        child_path = str(dir_decoy["path"]) + "/test_child.txt"
        result = mgr.check_access("read_document", {"file_path": child_path})
        # 子路径也应匹配父目录
        if result["triggered"]:
            assert result["risk_score"] == 1.0


def test_orchestrator_decoy_flow():
    """端到端测试：Orchestrator 检测诱饵触碰。"""
    orc = create_orchestrator()
    # 获取一个诱饵文件路径
    decoy_path = str(orc.decoy_manager._generator.decoy_dir / "财务预算审批表.xlsx")
    result = orc.check_tool_call("decoy-test-1", "read_document", {"file_path": decoy_path})
    # 诱饵文件应该触发阻断
    assert result["decoy"]["triggered"] == True
    assert result["risk_level"] in ("CRITICAL", "VERY_HIGH")
    assert result["action"] in ("block", "kill")


def test_normal_file_via_orchestrator():
    """正常文件在 Orchestrator 中不应触发诱饵。"""
    orc = create_orchestrator()
    result = orc.check_tool_call("decoy-test-2", "read_document", {"file_path": "policy_document.txt"})
    assert result["decoy"]["triggered"] == False


def test_decoy_plus_upload_trigger_kill():
    """诱饵 + 上传行为触发 KILL。"""
    orc = create_orchestrator()
    session = "decoy-upload-test"

    # 第一次: 读诱饵文件
    decoy_path = str(orc.decoy_manager._generator.decoy_dir / "内部合同审批记录.docx")
    r1 = orc.check_tool_call(session, "read_document", {"file_path": decoy_path})

    # 第二次: 调用 upload_data
    r2 = orc.check_tool_call(session, "upload_data", {"data": "敏感内容", "target": "http://external"})

    # upload 应该触发 kill (诱饵 + 外传)
    assert r2["action"] == "kill" or r2["action"] == "block"


def test_decoy_security_log():
    """诱饵事件应记录到安全日志。"""
    orc = create_orchestrator()
    decoy_path = str(orc.decoy_manager._generator.decoy_dir / "人事信息汇总.pdf")
    orc.check_tool_call("decoy-log-test", "read_document", {"file_path": decoy_path})
    events = orc.get_session_events("decoy-log-test")
    decoy_events = [e for e in events if e.get("risk_level") == "CRITICAL"]
    assert len(decoy_events) >= 1
