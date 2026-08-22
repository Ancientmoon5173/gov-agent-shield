"""
Audit 字段级校验器。

只读取 runner 捕获的 SecurityLogger 原始事件，不调用安全模块。
"""

import json
from typing import Any, Dict, List


TOOL_REQUIRED_FIELDS = {
    "event_id": lambda e: e.get("id") is not None,
    "timestamp": lambda e: bool(e.get("timestamp")),
    "session_id": lambda e: bool(e.get("session_id")),
    "tool_name": lambda e: bool(e.get("tool_name")),
    "tool_params": lambda e: bool(e.get("tool_params")),
    "action": lambda e: bool(e.get("disposition")),
    "risk_score": lambda e: e.get("risk_score") is not None,
    "risk_level": lambda e: bool(e.get("risk_level")),
    "policy_id": lambda e: bool(e.get("policy_id")),
    "decision_reason": lambda e: bool(e.get("decision_reason")),
    "defense_stage": lambda e: bool(e.get("defense_stage")),
    "chain_summary": lambda e: bool(e.get("chain_summary")),
    "asset_context": lambda e: _has_detail_key(e, "asset"),
}

BASIC_REQUIRED_FIELDS = {
    "event_id": lambda e: e.get("id") is not None,
    "timestamp": lambda e: bool(e.get("timestamp")),
    "session_id": lambda e: bool(e.get("session_id")),
    "event_type": lambda e: bool(e.get("event_type")),
}


DECOY_REQUIRED_FIELDS = {
    **BASIC_REQUIRED_FIELDS,
    "original_target": lambda e: _has_detail_key(e, "original_target"),
    "redirect_target": lambda e: _has_detail_key(e, "redirect_target"),
    "modified_params": lambda e: _has_detail_key(e, "modified_params"),
}


DPT_REQUIRED_FIELDS = {
    **BASIC_REQUIRED_FIELDS,
    "token": lambda e: _has_detail_key(e, "token"),
    "session_id": lambda e: bool(e.get("session_id")),
    "source_copy": lambda e: _has_dpt_source(e),
    "leak_event": lambda e: e.get("event_type")
    == "data_provenance_leak_detected",
}


def _details(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("details")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _has_detail_key(event: Dict[str, Any], key: str) -> bool:
    return key in _details(event)


def _has_dpt_source(event: Dict[str, Any]) -> bool:
    details = _details(event)
    token_info = details.get("token_info") or {}
    metadata = token_info.get("metadata") or {}
    return bool(metadata.get("copy_path") or metadata.get("source"))


def validate_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """校验单个审计事件的必需字段。"""
    event_type = str(event.get("event_type", ""))
    if event_type == "decoy_route_triggered":
        required = DECOY_REQUIRED_FIELDS
    elif event_type == "data_provenance_leak_detected":
        required = DPT_REQUIRED_FIELDS
    elif event.get("check_type") == "tool_call":
        required = TOOL_REQUIRED_FIELDS
    else:
        required = BASIC_REQUIRED_FIELDS

    missing = [
        field for field, check in required.items()
        if not check(event)
    ]
    return {
        "event_id": event.get("id"),
        "event_type": event_type,
        "required_field_count": len(required),
        "valid_field_count": len(required) - len(missing),
        "missing_fields": missing,
        "valid": not missing,
    }


def validate_case(result: Dict[str, Any]) -> Dict[str, Any]:
    """校验一个 case 的全部审计事件。"""
    event_records = result.get("audit_event_records", [])
    checks = [validate_event(event) for event in event_records]
    required_total = sum(c["required_field_count"] for c in checks)
    valid_total = sum(c["valid_field_count"] for c in checks)
    return {
        "case_id": result.get("case_id"),
        "event_count": len(checks),
        "required_field_count": required_total,
        "valid_field_count": valid_total,
        "field_completeness": (
            round(valid_total / required_total, 4)
            if required_total
            else 1.0
        ),
        "event_checks": checks,
    }


def build_field_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """生成 audit_field_report 结构。"""
    case_reports = [validate_case(result) for result in results]
    required_total = sum(r["required_field_count"] for r in case_reports)
    valid_total = sum(r["valid_field_count"] for r in case_reports)
    return {
        "schema_version": "1.0",
        "source": "audit_validator",
        "summary": {
            "case_count": len(results),
            "required_field_count": required_total,
            "valid_field_count": valid_total,
            "field_completeness": (
                round(valid_total / required_total, 4)
                if required_total
                else 1.0
            ),
        },
        "cases": case_reports,
    }
