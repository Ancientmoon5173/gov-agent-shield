"""
SecurityOutputCheck API 测试。

覆盖：
- 普通文本（无敏感数据）
- 身份证泄露（检测 + 脱敏）
- 手机号泄露（检测 + 脱敏）
- API Key 泄露（检测 + 脱敏）
"""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_normal_text_no_sensitive():
    """普通文本不应触发敏感检测。"""
    r = client.post("/security/check_output", json={
        "tool_name": "read_document",
        "output_text": "这是一段普通的政策文件内容。",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["has_sensitive_data"] is False
    assert data["masked_output"] == "这是一段普通的政策文件内容。"
    assert data["findings"] == []
    assert data["risk_level"] == "LOW"


def test_id_card_leak_detected_and_masked():
    """身份证号应被检测并脱敏。"""
    r = client.post("/security/check_output", json={
        "tool_name": "query_citizen_info",
        "output_text": "居民身份证号：110101199001011234",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["has_sensitive_data"] is True
    # 脱敏后不应包含完整身份证号
    assert "110101199001011234" not in data["masked_output"]
    # 应保留部分可识别信息
    assert "1101" in data["masked_output"]
    assert len(data["findings"]) > 0
    assert data["risk_level"] in ("VERY_HIGH", "CRITICAL")


def test_phone_leak_detected_and_masked():
    """手机号应被检测并脱敏。"""
    r = client.post("/security/check_output", json={
        "tool_name": "query_citizen_info",
        "output_text": "联系电话：13912345678",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["has_sensitive_data"] is True
    assert "13912345678" not in data["masked_output"]
    assert len(data["findings"]) > 0
    assert data["risk_level"] in ("HIGH", "VERY_HIGH", "CRITICAL")


def test_api_key_leak_detected_and_masked():
    """API Key 应被检测并脱敏。"""
    r = client.post("/security/check_output", json={
        "tool_name": "read_document",
        "output_text": "服务密钥：sk-abcdefghijklmnopqrstuvwxyz1234567890",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["has_sensitive_data"] is True
    assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in data["masked_output"]
    assert len(data["findings"]) > 0
    assert data["risk_level"] in ("VERY_HIGH", "CRITICAL")


def test_session_id_and_context_accepted():
    """session_id 和 context 应被接受。"""
    r = client.post("/security/check_output", json={
        "tool_name": "read_document",
        "output_text": "普通内容",
        "session_id": "test-session",
        "context": {"channel": "openclaw"},
    })
    assert r.status_code == 200
    assert r.json()["has_sensitive_data"] is False
