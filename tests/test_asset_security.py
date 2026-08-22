"""
Phase 1：AssetResolver 资产身份闭环测试。

覆盖：
- 企业联系人信息.xlsx -> personal_information / HIGH
- 数据库连接配置.txt -> credential / CRITICAL
- 真实 OpenClaw read 工具名下敏感资产必须提升决策
- 普通 policy.pdf 不产生资产风险
"""

from src.security import create_orchestrator
from src.security.asset_resolver import AssetResolver


def test_resolve_contact_asset():
    resolver = AssetResolver()
    result = resolver.resolve("read", {"path": "企业联系人信息.xlsx"})

    assert result["matched"] is True
    assert result["asset_type"] == "personal_information"
    assert result["sensitivity"] == "HIGH"
    assert result["owner"] == "数据管理科"
    assert result["sharing_policy"] == "REVIEW_REQUIRED"
    assert result["risk_score"] == 0.6


def test_resolve_credential_asset():
    resolver = AssetResolver()
    result = resolver.resolve("read", {"path": "数据库连接配置.txt"})

    assert result["matched"] is True
    assert result["asset_type"] == "credential"
    assert result["sensitivity"] == "CRITICAL"
    assert result["owner"] == "信息中心"
    assert result["sharing_policy"] == "BLOCK"
    assert result["risk_score"] == 0.9


def test_contact_read_not_allowed():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "asset-security-contact",
        "read",
        {"path": "企业联系人信息.xlsx"},
        agent_id="admin_agent",
    )

    assert result["asset"]["matched"] is True
    assert result["asset"]["asset_type"] == "personal_information"
    assert result["risk_score"] >= 0.5
    assert result["action"] != "allow"


def test_credential_read_blocked():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "asset-security-credential",
        "read",
        {"path": "数据库连接配置.txt"},
        agent_id="admin_agent",
    )

    assert result["asset"]["matched"] is True
    assert result["asset"]["asset_type"] == "credential"
    assert result["action"] in ("block", "kill")


def test_normal_file_has_no_asset_risk():
    orc = create_orchestrator()
    result = orc.check_tool_call(
        "asset-security-normal",
        "read",
        {"path": "policy.pdf"},
        agent_id="admin_agent",
    )

    assert result["asset"]["matched"] is False
    assert result["asset"]["risk_score"] == 0
    assert result["action"] not in ("block", "kill")
