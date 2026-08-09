"""
数据分类器测试。

覆盖：
- customer.xlsx upload -> SENSITIVE
- public_notice.pdf -> PUBLIC
- 内部资料路径 -> INTERNAL
- 绝密关键词 -> CRITICAL
- 数据分级接入 SecurityOrchestrator 的 tool risk 修正
"""

from src.security import create_orchestrator
from src.security.data_classifier import DataClassifier


def test_customer_upload_sensitive():
    """客户数据上传应识别为 SENSITIVE。"""
    classifier = DataClassifier()
    result = classifier.classify(
        "upload_data",
        {"data": "customer_records.xlsx", "target": "external"},
    )
    assert result["data_class"] == "SENSITIVE"
    assert result["risk_score"] == 0.7
    assert result["findings"]


def test_public_notice_public():
    """公开通知文件应识别为 PUBLIC。"""
    classifier = DataClassifier()
    result = classifier.classify(
        "read_document",
        {"file_path": "public_notice.pdf"},
    )
    assert result["data_class"] == "PUBLIC"
    assert result["risk_score"] == 0.0
    assert result["findings"] == []


def test_internal_path_internal():
    """internal 路径应识别为 INTERNAL。"""
    classifier = DataClassifier()
    result = classifier.classify(
        "read_document",
        {"file_path": "documents/internal_plan.md"},
    )
    assert result["data_class"] == "INTERNAL"
    assert result["risk_score"] == 0.4


def test_top_secret_critical():
    """绝密关键词应识别为 CRITICAL。"""
    classifier = DataClassifier()
    result = classifier.classify(
        "read_document",
        {"file_path": "top_secret_report.md"},
    )
    assert result["data_class"] == "CRITICAL"
    assert result["risk_score"] == 0.9


def test_orchestrator_data_context():
    """SecurityOrchestrator 应输出 data_class 并修正 tool risk。"""
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "data-test",
        "upload_data",
        {"data": "customer_records.xlsx", "target": "external"},
        agent_id="admin_agent",
    )
    assert result["data_class"] == "SENSITIVE"
    assert result["data_findings"]
