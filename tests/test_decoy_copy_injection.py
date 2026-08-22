"""
方案 C-2a / C-2b 测试。

覆盖：
- 诱饵副本生成并预埋数据溯源令牌
- 会话注入上限
- 文件名穿越防护
- Orchestrator 对敏感读取返回 inject_token（C-2b）
- 注入令牌可被外发扫描命中
"""

from src.security import create_orchestrator
from src.security.decoy_copy_generator import create_decoy_copy_generator


def test_generate_copy_with_token(tmp_path):
    generator = create_decoy_copy_generator(config={"root": tmp_path})

    result = generator.create_copy(
        session_id="sess-copy-1",
        asset_type="customer_data",
        filename="customer_records.xlsx",
    )

    assert result["created"] is True
    assert result["token"].startswith("DPT")
    copy_path = tmp_path / "sess-copy-1" / "customer_data" / "customer_records.xlsx"
    assert result["copy_path"] == str(copy_path)
    assert copy_path.exists()
    content = copy_path.read_text(encoding="utf-8")
    assert result["token"] in content
    assert generator.tracker.active_count("sess-copy-1") == 1


def test_max_injections_per_session(tmp_path):
    generator = create_decoy_copy_generator(
        config={"root": tmp_path, "max_injections_per_session": 1}
    )

    first = generator.create_copy(
        session_id="sess-limit", asset_type="contract", filename="a.docx"
    )
    second = generator.create_copy(
        session_id="sess-limit", asset_type="contract", filename="b.docx"
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["reason"] == "max_injections_reached"


def test_filename_traversal_sanitized(tmp_path):
    generator = create_decoy_copy_generator(config={"root": tmp_path})

    result = generator.create_copy(
        session_id="sess-safe",
        asset_type="financial_document",
        filename="../../evil.xlsx",
    )

    assert result["created"] is True
    assert ".." not in result["copy_path"]
    assert result["copy_path"].startswith(str(tmp_path))


def test_invalid_filename_rejected(tmp_path):
    generator = create_decoy_copy_generator(config={"root": tmp_path})

    result = generator.create_copy(
        session_id="sess-bad", asset_type="contract", filename="."
    )

    assert result["created"] is False
    assert result["reason"] == "invalid_filename"


def test_orchestrator_inject_token_on_sensitive_read():
    orc = create_orchestrator()
    orc.decoy_manager._route_config["dry_run"] = True
    session_id = "sess-inject-token"

    result = orc.check_tool_call(
        session_id,
        "read_document",
        {"file_path": "customer_records.xlsx"},
        agent_id="admin_agent",
    )

    assert result["inject_token"] is not None
    token = result["inject_token"]["token"]
    assert token.startswith("DPT")
    assert result["inject_token"]["policy_id"].startswith(
        "data_provenance:inject:"
    )

    # 注入的令牌可被外发扫描命中
    leak = orc.data_provenance_tracker.scan_leak(
        "send_email", {"body": f"附件内容 {token}"}
    )
    assert leak["hit"] is True
    assert leak["token"] == token


def test_orchestrator_no_inject_token_on_public_read():
    orc = create_orchestrator()

    result = orc.check_tool_call(
        "sess-inject-none",
        "read_document",
        {"file_path": "public_notice.md"},
        agent_id="admin_agent",
    )

    assert result["inject_token"] is None
