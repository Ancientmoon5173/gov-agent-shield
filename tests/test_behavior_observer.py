"""
行为特征观察器（方案 B）测试。

覆盖：
- 敏感资产 + 虚拟规则命中 → virtual_hit，低权重 increment
- 普通文件不触发
- 前序命中提升 confidence
- SecurityOrchestrator 接入并产生 decoy_virtual_hit 审计
"""

from src.security import create_orchestrator
from src.security.behavior_observer import BehaviorObserver


RULES = [
    {
        "rule_id": "virtual-fin-001",
        "target_tools": ["read_document"],
        "patterns": ["预算", "财务"],
        "min_sensitivity": "HIGH",
        "base_confidence": 0.3,
        "risk_increment": 0.05,
    }
]


def test_sensitive_asset_virtual_hit_low_weight():
    observer = BehaviorObserver(rules=RULES)
    result = observer.observe(
        "read_document",
        {"file_path": "财务预算审批表.xlsx"},
        {
            "matched": True,
            "sensitivity": "HIGH",
            "asset_type": "financial_document",
        },
    )
    assert result["virtual_hit"] is True
    assert result["rule_id"] == "virtual-fin-001"
    assert result["risk_increment"] <= 0.05


def test_normal_file_no_virtual_hit():
    observer = BehaviorObserver(rules=RULES)
    result = observer.observe(
        "read_document",
        {"file_path": "public_notice.md"},
        {"matched": False, "sensitivity": "LOW"},
    )
    assert result["virtual_hit"] is False


def test_prior_hits_increase_confidence():
    observer = BehaviorObserver(rules=RULES)
    base = observer.observe(
        "read_document",
        {"file_path": "财务预算审批表.xlsx"},
        {"matched": True, "sensitivity": "HIGH"},
        prior_hits=0,
    )
    repeat = observer.observe(
        "read_document",
        {"file_path": "财务预算审批表.xlsx"},
        {"matched": True, "sensitivity": "HIGH"},
        prior_hits=2,
    )
    assert repeat["confidence"] > base["confidence"]


def test_orchestrator_observer_audit():
    orc = create_orchestrator()
    session_id = "observer-test"
    result = orc.check_tool_call(
        session_id,
        "read_document",
        {"file_path": "财务预算审批表.xlsx"},
        agent_id="admin_agent",
    )
    events = orc.security_logger.get_session_events(session_id)
    hits = [e for e in events if e.get("event_type") == "decoy_virtual_hit"]
    assert hits
    assert result["asset"]["matched"] is True
