"""
AssetResolver 测试。

覆盖：
- 财务预算文件 → financial_document / HIGH
- 员工工资文件 → personnel_record / CRITICAL
- 客户名单文件 → customer_data / SENSITIVE
- 普通文件不匹配
- SecurityOrchestrator 返回 asset 标签
"""

from src.security import create_orchestrator
from src.security.asset_resolver import AssetResolver


def test_finance_asset_resolved():
    resolver = AssetResolver()
    result = resolver.resolve(
        "read_document",
        {"file_path": "财务预算审批表.xlsx"},
    )
    assert result["matched"] is True
    assert result["asset_type"] == "financial_document"
    assert result["sensitivity"] == "HIGH"
    assert result["owner"] == "finance_department"


def test_staff_asset_resolved():
    resolver = AssetResolver()
    result = resolver.resolve(
        "read_document",
        {"file_path": "员工工资.xlsx"},
    )
    assert result["matched"] is True
    assert result["asset_type"] == "personnel_record"
    assert result["sensitivity"] == "CRITICAL"


def test_customer_asset_resolved():
    resolver = AssetResolver()
    result = resolver.resolve(
        "upload_data",
        {"data": "customer_records.xlsx", "target": "external"},
    )
    assert result["matched"] is True
    assert result["asset_type"] == "customer_data"
    assert result["sensitivity"] == "SENSITIVE"


def test_normal_file_not_matched():
    resolver = AssetResolver()
    result = resolver.resolve(
        "read_document",
        {"file_path": "public_notice.md"},
    )
    assert result["matched"] is False
    assert result["policy"] == "allow"


def test_orchestrator_asset_context():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "asset-test",
        "upload_data",
        {"data": "customer_records.xlsx", "target": "http://external"},
        agent_id="admin_agent",
    )
    assert result["asset"]["matched"] is True
    assert result["asset"]["asset_type"] == "customer_data"
