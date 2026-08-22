"""
最小可复现 E2E Agent Benchmark。

固定 prompt + 固定 Agent trace，验证
OpenClaw Plugin 契约 -> HTTP /security/check_tool -> Security Engine 链路。
"""

import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "benchmark"))

from fastapi.testclient import TestClient  # noqa: E402
from metrics.audit_validator import build_field_report  # noqa: E402
from src.main import app, get_security_orchestrator  # noqa: E402

from openclaw_adapter import build_tool_request, send_tool_request  # noqa: E402


E2E_CASES_DIR = PROJECT_ROOT / "benchmark" / "e2e_cases"
OUTPUT_DIR = PROJECT_ROOT / "benchmark" / "outputs"


def replace_dpt_token(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace("__DPT_TOKEN__", token)
    if isinstance(value, dict):
        return {
            key: replace_dpt_token(item, token)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [replace_dpt_token(item, token) for item in value]
    return value


def load_cases() -> List[Dict[str, Any]]:
    cases = []
    for path in sorted(E2E_CASES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def run_case(
    client,
    orchestrator,
    case: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:
    case_id = str(case["case_id"])
    session_id = f"{case_id}-{run_id}"
    orchestrator.start_session(session_id)
    expected_plan = list(case.get("expected_tool_plan", []))

    input_context = None
    document_context = case.get("document_context", "")
    if document_context:
        input_context = orchestrator.check_input(
            session_id,
            str(case.get("user_input", "")),
            context_text=document_context,
        )

    if not expected_plan:
        return {
            "case_id": case_id,
            "scenario": case.get("scenario"),
            "user_input": case.get("user_input"),
            "expected": {
                "expected_result_type": case.get("expected_result_type"),
                "expected_final_action": case.get("expected_final_action"),
                "required_audit_events": case.get(
                    "required_audit_events", []
                ),
            },
            "document_context": document_context,
            "input_context": input_context,
            "tool_calls": [],
            "security_decisions": [],
            "agent_trace": [],
            "audit_events": [],
            "audit_event_records": [],
            "audit_event_types": [],
            "result_type": "no_tool_call",
            "final_action": "no_tool_call",
            "review_denied": False,
            "latencies_ms": [],
        }

    pending_token = None
    tool_calls: List[Dict[str, Any]] = []
    security_decisions: List[Dict[str, Any]] = []
    agent_trace: List[Dict[str, Any]] = []
    latencies: List[float] = []
    result_type = "engine_allow"
    final_action = "allow"
    review_denied = False

    for step_index, step in enumerate(expected_plan, start=1):
        tool_name = str(step["tool_name"])
        params = copy.deepcopy(step.get("params", {}))
        if pending_token:
            params = replace_dpt_token(params, pending_token)

        request = build_tool_request(
            session_id=session_id,
            agent_id="main",
            tool_name=tool_name,
            parameters=params,
            task_context=case.get("task_context", {}),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        start = time.perf_counter()
        decision = send_tool_request(client, request)
        latency_ms = round((time.perf_counter() - start) * 1000, 4)
        latencies.append(latency_ms)

        security_decisions.append(decision)
        tool_calls.append({
            "tool_name": tool_name,
            "params": params,
            "action": decision.get("action"),
        })
        agent_trace.append({
            "step": step_index,
            "tool_name": tool_name,
            "params": params,
            "action": decision.get("action"),
            "risk_score": decision.get("risk_score"),
            "risk_level": decision.get("risk_level"),
            "policy_id": decision.get("policy_id"),
            "decision_reason": decision.get("decision_reason")
            or decision.get("reason"),
            "defense_stage": decision.get("defense_stage"),
            "latency_ms": latency_ms,
        })

        if decision.get("inject_token") and pending_token is None:
            pending_token = decision["inject_token"]["token"]

        action = decision.get("action")
        if action in ("block", "kill"):
            result_type = "engine_block"
            final_action = action
            break
        if action == "review":
            if case.get("approval_mode") == "auto-deny":
                result_type = "review_denied"
                final_action = "review"
                review_denied = True
                agent_trace[-1]["approval"] = "deny"
                break
            result_type = "review_allowed"
            final_action = "review"
            agent_trace[-1]["approval"] = "allow-once"
            continue

    events = orchestrator.security_logger.get_session_events(session_id)
    event_types = sorted(
        {str(e.get("event_type", "")) for e in events if e.get("event_type")}
    )

    return {
        "case_id": case_id,
        "session_id": session_id,
        "scenario": case.get("scenario"),
        "user_input": case.get("user_input"),
        "expected": {
            "expected_result_type": case.get("expected_result_type"),
            "expected_final_action": case.get("expected_final_action"),
            "required_audit_events": case.get("required_audit_events", []),
        },
        "document_context": document_context,
        "input_context": input_context,
        "tool_calls": tool_calls,
        "security_decisions": security_decisions,
        "agent_trace": agent_trace,
        "audit_events": event_types,
        "audit_event_records": events,
        "audit_event_types": event_types,
        "result_type": result_type,
        "final_action": final_action,
        "review_denied": review_denied,
        "latencies_ms": latencies,
    }


def compute_e2e_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    tool_call_cases = [r for r in results if r["result_type"] != "no_tool_call"]
    no_tool_call_count = total - len(tool_call_cases)
    tool_execution_rate = (
        round(len(tool_call_cases) / total, 4) if total else 0.0
    )
    no_tool_call_rate = (
        round(no_tool_call_count / total, 4) if total else 0.0
    )

    review_cases = [
        r for r in tool_call_cases
        if r["result_type"] in ("engine_review", "review_allowed", "review_denied")
    ]
    review_denied_count = sum(
        1 for r in tool_call_cases if r["result_type"] == "review_denied"
    )
    engine_block_count = sum(
        1 for r in tool_call_cases if r["result_type"] == "engine_block"
    )
    review_rate = (
        round(len(review_cases) / len(tool_call_cases), 4)
        if tool_call_cases
        else 0.0
    )
    escalation_rate = (
        round(review_denied_count / len(review_cases), 4)
        if review_cases
        else 0.0
    )
    engine_block_rate = (
        round(engine_block_count / len(tool_call_cases), 4)
        if tool_call_cases
        else 0.0
    )

    expected_blocked = [
        r for r in tool_call_cases
        if r["expected"]["expected_result_type"] == "engine_block"
    ]
    tp = sum(
        1 for r in expected_blocked if r["result_type"] == "engine_block"
    )
    fn = len(expected_blocked) - tp
    other = [
        r for r in tool_call_cases
        if r["expected"]["expected_result_type"] != "engine_block"
    ]
    fp = sum(1 for r in other if r["result_type"] == "engine_block")
    tn = len(other) - fp

    precision = (
        round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    )
    recall = (
        round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    )
    false_positive_rate = (
        round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0
    )

    return {
        "sample_counts": {
            "total": total,
            "tool_call": len(tool_call_cases),
            "no_tool_call": no_tool_call_count,
        },
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "tool_execution_rate": tool_execution_rate,
        "no_tool_call_rate": no_tool_call_rate,
        "review_rate": review_rate,
        "escalation_rate": escalation_rate,
        "engine_block_rate": engine_block_rate,
        "confusion_matrix": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        },
        "review_denied_count": review_denied_count,
    }


def main() -> int:
    cases = load_cases()
    client = TestClient(app)
    orchestrator = get_security_orchestrator()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = [run_case(client, orchestrator, case, run_id) for case in cases]
    metrics = compute_e2e_metrics(results)
    audit_report = build_field_report(results)
    metrics["audit_field_completeness"] = audit_report["summary"][
        "field_completeness"
    ]

    latencies = [
        latency
        for result in results
        for latency in result["latencies_ms"]
    ]
    average_latency = round(sum(latencies) / len(latencies), 4) if latencies else 0.0
    ordered = sorted(latencies)
    p95 = ordered[max(0, int(0.95 * len(ordered)) - 1)] if ordered else 0.0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUTPUT_DIR / "e2e_raw_results.json"
    metrics_path = OUTPUT_DIR / "e2e_metrics_report.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "source": "e2e_benchmark",
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "source": "e2e_benchmark",
                "metrics": metrics,
                "performance": {
                    "average_latency_ms": average_latency,
                    "p95_latency_ms": p95,
                    "count": len(latencies),
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("E2E benchmark completed")
    print(f"total={metrics['sample_counts']['total']}")
    print(f"tool_call={metrics['sample_counts']['tool_call']}")
    print(f"no_tool_call={metrics['sample_counts']['no_tool_call']}")
    print(f"tool_execution_rate={metrics['tool_execution_rate']}")
    print(f"no_tool_call_rate={metrics['no_tool_call_rate']}")
    print(f"review_rate={metrics['review_rate']}")
    print(f"escalation_rate={metrics['escalation_rate']}")
    print(f"engine_block_rate={metrics['engine_block_rate']}")
    print(f"precision={metrics['precision']}")
    print(f"recall={metrics['recall']}")
    print(f"false_positive_rate={metrics['false_positive_rate']}")
    print(f"audit_field_completeness={metrics['audit_field_completeness']}")
    print(f"raw_results={raw_path}")
    print(f"metrics_report={metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
