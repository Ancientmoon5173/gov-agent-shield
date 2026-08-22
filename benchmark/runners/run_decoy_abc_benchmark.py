"""
Decoy ABC 专项 benchmark runner。

验证 Shadow Route / Behavioral Decoy / Data Provenance Token 的字段级能力，
只调用现有安全模块，不修改任何核心逻辑。
"""

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "benchmark"))

from src.security import create_orchestrator  # noqa: E402
from src.security.data_provenance import DataProvenanceTracker  # noqa: E402


BENCHMARK_DIR = PROJECT_ROOT / "benchmark"
CASES_PATH = BENCHMARK_DIR / "cases" / "decoy_abc_cases.json"
OUTPUT_PATH = BENCHMARK_DIR / "outputs" / "decoy_abc_report.json"


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


def _detail_value(event: Dict[str, Any], key: str) -> Any:
    details = event.get("details")
    if isinstance(details, dict):
        return details.get(key)
    if isinstance(details, str):
        try:
            return json.loads(details).get(key)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _dpt_source_copy(event: Dict[str, Any]) -> bool:
    token_info = _detail_value(event, "token_info") or {}
    metadata = token_info.get("metadata") or {}
    return bool(metadata.get("copy_path") or metadata.get("source"))


def run_engine_case(
    orchestrator,
    case: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:
    session_id = f"{case['case_id']}-{run_id}"
    orchestrator.start_session(session_id)
    pending_token = None
    token_source = ""
    steps: List[Dict[str, Any]] = []

    for step in case.get("reference_plan", []):
        tool_name = str(step["tool_name"])
        params = copy.deepcopy(step.get("params", {}))
        if pending_token:
            params = replace_dpt_token(params, pending_token)
        result = orchestrator.check_tool_call(
            session_id,
            tool_name,
            params,
            agent_id="admin_agent",
            task_context=case.get("task_context", {}),
        )
        if pending_token is None:
            if result.get("inject_token"):
                pending_token = result["inject_token"]["token"]
                token_source = "tool_result_inject"
            elif result.get("decoy_route", {}).get("token"):
                pending_token = result["decoy_route"]["token"]
                token_source = "decoy_copy"

        steps.append({
            "tool_name": tool_name,
            "params": params,
            "action": result.get("action"),
            "risk_score": result.get("risk_score"),
            "risk_level": result.get("risk_level"),
            "policy_id": result.get("policy_id"),
            "inject_token_generated": bool(result.get("inject_token")),
            "decoy_route": result.get("decoy_route"),
            "data_provenance_hit": bool(
                result.get("data_provenance", {}).get("hit")
            ),
            "behavior_signal": result.get("behavior", {}).get(
                "behavior_signal", {}
            ),
        })

    events = orchestrator.security_logger.get_session_events(session_id)
    final_step = steps[-1] if steps else {}
    return {
        "case_id": case["case_id"],
        "session_id": session_id,
        "steps": steps,
        "final_action": final_step.get("action", "allow"),
        "pending_token": pending_token,
        "token_source": token_source,
        "events": events,
        "event_types": sorted(
            {str(e.get("event_type", "")) for e in events if e.get("event_type")}
        ),
    }


def run_lifecycle_case() -> Dict[str, bool]:
    tracker = DataProvenanceTracker()
    tracker.register("decoy-lifecycle", "call-1", "DPT-lifecycle-001")
    register_ok = tracker.active_count("decoy-lifecycle") == 1

    tracker.revoke("DPT-lifecycle-001")
    revoked = tracker.scan_leak(
        "upload_file",
        {"body": "DPT-lifecycle-001"},
    )
    revoke_ok = revoked["hit"] is False

    tracker.register("decoy-lifecycle", "call-2", "DPT-lifecycle-002")
    tracker._tokens["DPT-lifecycle-002"]["expires_at"] = 0
    expired = tracker.scan_leak(
        "upload_file",
        {"body": "DPT-lifecycle-002"},
    )
    expired_ok = expired["hit"] is False

    return {
        "register": register_ok,
        "revoke_works": revoke_ok,
        "expired_ignored": expired_ok,
    }


def check_engine_case(
    case: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    expected = case.get("expected", {})
    component = case["component"]
    checks: Dict[str, Any] = {}

    if component == "A":
        route = next(
            (
                step.get("decoy_route") or {}
                for step in result["steps"]
                if step.get("decoy_route", {}).get("matched")
            ),
            {},
        )
        expected_route = expected.get("decoy_route", {})
        expected_matched = bool(expected_route.get("matched", False))
        checks["matched"] = bool(route.get("matched")) == expected_matched
        checks["enabled"] = bool(route.get("enabled")) == bool(
            expected_route.get("enabled", False)
        )
        if expected_matched:
            checks["original_target"] = bool(route.get("original_target"))
            checks["redirect_target"] = bool(route.get("redirect_target"))
            checks["modified_params"] = bool(route.get("modified_params"))
            if expected.get("copy_exists"):
                checks["copy_exists"] = bool(
                    route.get("redirect_target")
                    and Path(route["redirect_target"]).exists()
                )
        else:
            checks["original_target"] = not bool(route.get("original_target"))
            checks["redirect_target"] = not bool(route.get("redirect_target"))
            checks["modified_params"] = not bool(route.get("modified_params"))

    elif component == "B":
        virtual_events = [
            e for e in result["events"]
            if e.get("event_type") == "decoy_virtual_hit"
        ]
        checks["virtual_hit"] = bool(virtual_events)
        checks["confidence"] = bool(
            virtual_events
            and float(
                _detail_value(virtual_events[-1], "confidence") or 0.0
            )
            >= float(expected.get("confidence_min", 0.0))
        )
        checks["risk_increment"] = bool(
            virtual_events
            and float(
                _detail_value(virtual_events[-1], "risk_increment") or 1.0
            )
            <= float(expected.get("risk_increment_max", 0.05))
        )
        checks["evidence"] = bool(
            result["steps"]
            and result["steps"][-1].get("behavior_signal", {}).get("evidence")
        )
        checks["not_blocked"] = result["final_action"] not in (
            "block",
            "kill",
        )

    elif component == "C":
        leak_events = [
            e for e in result["events"]
            if e.get("event_type") == "data_provenance_leak_detected"
        ]
        checks["token_generated"] = bool(result["pending_token"])
        checks["leak_detected"] = bool(leak_events)
        checks["blocked"] = result["final_action"] in ("block", "kill")
        checks["source_copy"] = bool(leak_events and _dpt_source_copy(leak_events[-1]))

    passed = all(checks.values())
    return {
        "case_id": case["case_id"],
        "component": component,
        "passed": passed,
        "checks": checks,
        "final_action": result["final_action"],
        "event_types": result["event_types"],
        "token_source": result.get("token_source", ""),
    }


def main() -> int:
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    orchestrator = create_orchestrator()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: List[Dict[str, Any]] = []

    for case in cases:
        if case.get("mode") == "lifecycle":
            lifecycle_checks = run_lifecycle_case()
            results.append({
                "case_id": case["case_id"],
                "component": case["component"],
                "passed": all(lifecycle_checks.values()),
                "checks": lifecycle_checks,
                "final_action": "lifecycle",
                "event_types": [],
                "token_source": "",
            })
            continue

        result = run_engine_case(orchestrator, case, run_id)
        results.append(check_engine_case(case, result))

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "decoy_abc_benchmark",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
        "results": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("Decoy ABC benchmark completed")
    print(f"total={total}")
    print(f"passed={passed}")
    print(f"failed={total - passed}")
    for result in results:
        print(
            f"{result['case_id']} {result['component']} "
            f"passed={result['passed']}"
        )
    print(f"report={OUTPUT_PATH}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
