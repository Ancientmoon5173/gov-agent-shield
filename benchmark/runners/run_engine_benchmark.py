"""
Engine benchmark runner。

直接复用 SecurityOrchestrator.check_tool_call / check_input，
不复制任何安全逻辑。
"""

import argparse
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

from metrics.audit_validator import build_field_report  # noqa: E402
from metrics.calculator import compute_metrics, compute_performance  # noqa: E402
from src.security import create_orchestrator  # noqa: E402


BENCHMARK_DIR = PROJECT_ROOT / "benchmark"
DEFAULT_OUTPUT_DIR = BENCHMARK_DIR / "outputs"


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def replace_dpt_token(value: Any, token: str) -> Any:
    """将样本中的 __DPT_TOKEN__ 占位符替换为运行时令牌。"""
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


def run_case(
    orchestrator,
    case: Dict[str, Any],
    case_type: str,
    expected: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:
    """运行单个 benchmark case。"""
    case_id = str(case["case_id"])
    session_id = f"{case_id}-{run_id}"
    orchestrator.start_session(session_id)

    input_result = None
    if case.get("input"):
        input_result = orchestrator.check_input(
            session_id,
            str(case["input"].get("user_input", "")),
            str(case["input"].get("context_text", "")),
        )

    pending_token = None
    steps: List[Dict[str, Any]] = []
    latencies: List[float] = []

    for step in case.get("reference_plan", []):
        tool_name = str(step["tool_name"])
        params = copy.deepcopy(step.get("params", {}))
        if pending_token:
            params = replace_dpt_token(params, pending_token)

        start = time.perf_counter()
        result = orchestrator.check_tool_call(
            session_id,
            tool_name,
            params,
            agent_id="admin_agent",
            task_context=case.get("task_context", {}),
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 4)
        latencies.append(latency_ms)

        if result.get("inject_token") and pending_token is None:
            pending_token = result["inject_token"]["token"]

        steps.append({
            "tool_name": tool_name,
            "params": params,
            "action": result.get("action"),
            "risk_score": result.get("risk_score"),
            "risk_level": result.get("risk_level"),
            "policy_id": result.get("policy_id"),
            "latency_ms": latency_ms,
            "inject_token_generated": bool(result.get("inject_token")),
            "decoy_route_triggered": bool(
                result.get("decoy_route", {}).get("matched")
            ),
            "decoy_route": result.get("decoy_route"),
            "data_provenance_hit": bool(
                result.get("data_provenance", {}).get("hit")
            ),
        })

    events = orchestrator.security_logger.get_session_events(session_id)
    audit_events = sorted(
        {str(e.get("event_type", "")) for e in events if e.get("event_type")}
    )

    final_step = steps[-1] if steps else {}
    final_action = str(
        final_step.get("action")
        or input_result.get("action", "allow")
    )
    required_audit_events = list(expected.get("required_audit_events", []))
    present_audit_events = set(audit_events)
    missing_audit_events = sorted(
        set(required_audit_events) - present_audit_events
    )

    return {
        "case_id": case_id,
        "session_id": session_id,
        "category": str(case.get("category", "")),
        "type": case_type,
        "scenario": str(case.get("scenario", "")),
        "expected": expected,
        "input_action": input_result.get("action") if input_result else None,
        "dpt_attempted": "__DPT_TOKEN__" in json.dumps(
            case.get("reference_plan", []),
            ensure_ascii=False,
        ),
        "review_denied": False,
        "steps": steps,
        "final_action": final_action,
        "final_risk_score": final_step.get("risk_score"),
        "final_risk_level": final_step.get("risk_level"),
        "final_policy_id": final_step.get("policy_id"),
        "recognized": final_action != "allow",
        "blocked": final_action in ("block", "kill"),
        "result_type": (
            "engine_block"
            if final_action in ("block", "kill")
            else "engine_review"
            if final_action == "review"
            else "engine_allow"
        ),
        "audit_events": audit_events,
        "audit_event_records": events,
        "missing_audit_events": missing_audit_events,
        "total_latency_ms": round(sum(latencies), 4),
    }


def run_benchmark(limit: int = 0) -> Dict[str, Any]:
    """运行全部 benchmark 样本。"""
    attack_cases = load_json(BENCHMARK_DIR / "attack_cases.json")
    normal_cases = load_json(BENCHMARK_DIR / "normal_cases.json")
    expected = load_json(BENCHMARK_DIR / "expected_result.json")["cases"]

    if limit > 0:
        attack_cases = attack_cases[:limit]
        normal_cases = normal_cases[:limit]

    orchestrator = create_orchestrator()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: List[Dict[str, Any]] = []
    all_latencies: List[float] = []

    for case in attack_cases:
        case_id = str(case["case_id"])
        result = run_case(
            orchestrator,
            case,
            "attack",
            expected.get(case_id, {}),
            run_id,
        )
        results.append(result)
        all_latencies.extend(
            step["latency_ms"] for step in result["steps"]
        )

    for case in normal_cases:
        case_id = str(case["case_id"])
        result = run_case(
            orchestrator,
            case,
            "normal",
            expected.get(case_id, {}),
            run_id,
        )
        results.append(result)
        all_latencies.extend(
            step["latency_ms"] for step in result["steps"]
        )

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "engine_benchmark",
        "results": results,
        "all_latencies_ms": all_latencies,
    }


def write_reports(data: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw_results.json"
    metrics_path = output_dir / "metrics_report.json"

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": data["schema_version"],
                "run_id": data["run_id"],
                "generated_at": data["generated_at"],
                "source": data["source"],
                "results": data["results"],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    metrics = compute_metrics(data["results"])
    performance = compute_performance(data["all_latencies_ms"])
    audit_report = build_field_report(data["results"])
    audit_path = output_dir / "audit_field_report.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_report, f, ensure_ascii=False, indent=2)

    metrics["audit_field_completeness"] = audit_report["summary"][
        "field_completeness"
    ]
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": data["schema_version"],
                "run_id": data["run_id"],
                "generated_at": data["generated_at"],
                "source": data["source"],
                "metrics": metrics,
                "performance": performance,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("Benchmark run completed")
    print(f"attack_samples={metrics['sample_counts']['attack']}")
    print(f"normal_samples={metrics['sample_counts']['normal']}")
    print(f"recognition_rate={metrics['recognition_rate']}")
    print(f"blocking_rate={metrics['blocking_rate']}")
    print(f"precision={metrics['precision']}")
    print(f"recall={metrics['recall']}")
    print(f"false_positive_rate={metrics['false_positive_rate']}")
    print(f"audit_completeness={metrics['audit_completeness']}")
    print(f"average_latency_ms={performance['average_latency_ms']}")
    print(f"p95_latency_ms={performance['p95_latency_ms']}")
    print(
        f"audit_field_completeness="
        f"{audit_report['summary']['field_completeness']}"
    )
    print(f"raw_results={raw_path}")
    print(f"metrics_report={metrics_path}")
    print(f"audit_field_report={audit_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GovAgent-Shield engine benchmark runner"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅运行前 N 个攻击/正常样本，0 表示全部",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="输出目录，默认 benchmark/outputs",
    )
    args = parser.parse_args()

    data = run_benchmark(limit=args.limit)
    write_reports(data, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
