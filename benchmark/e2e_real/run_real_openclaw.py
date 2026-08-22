"""
Phase 4.3-C 真实 OpenClaw E2E runner。

优先尝试真实 OpenClaw Agent + Plugin Hook 链路；
若环境无法自动化，自动降级为 TestClient 模拟链路，并在输出中明确标注。
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "benchmark"))

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app, get_security_orchestrator  # noqa: E402


E2E_REAL_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = E2E_REAL_DIR / "scenarios"
OUTPUT_DIR = E2E_REAL_DIR / "outputs"
STATE_DIR = E2E_REAL_DIR / ".openclaw-state"
DEFAULT_OPENCLAW_DIR = Path(r"D:\OpenClaw\openclaw-main")
DEFAULT_CONFIG_PATH = Path(r"C:\Users\ancientmoon\.openclaw\openclaw.json")


def load_scenarios() -> List[Dict[str, Any]]:
    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            scenarios.append(json.load(f))
    return scenarios


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


def _extract_field(block: str, marker: str) -> str:
    for line in block.splitlines():
        if marker in line:
            return line.split(marker, 1)[-1].strip()
    return ""


def parse_shield_blocks(stdout: str) -> List[Dict[str, Any]]:
    decisions: List[Dict[str, Any]] = []
    for block in stdout.split("========== GovAgent Shield ==========")[1:]:
        decision = {
            "tool_name": _extract_field(block, "[ToolCall] tool:"),
            "args": _extract_field(block, "args:"),
            "risk_score": _extract_field(block, "[Security] risk:"),
            "policy_id": _extract_field(block, "policy:"),
            "defense_stage": _extract_field(block, "stage:"),
            "action": _extract_field(block, "decision:"),
            "reason": _extract_field(block, "reason:"),
        }
        if decision["tool_name"]:
            decisions.append(decision)
    return decisions


def _is_real_available(openclaw_dir: Path) -> bool:
    return (
        (openclaw_dir / "openclaw.mjs").exists()
        and DEFAULT_CONFIG_PATH.exists()
    )


def run_real_case(
    case: Dict[str, Any],
    openclaw_dir: Path,
    timeout: int,
    run_id: str,
) -> Dict[str, Any]:
    """通过真实 OpenClaw CLI 运行一个固定 prompt。"""
    from src.security import create_orchestrator

    orchestrator = create_orchestrator()
    before_events = orchestrator.security_logger.get_recent_events(1000)
    before_max = max((e["id"] for e in before_events), default=0)

    case_id = str(case["case_id"])
    message_path = OUTPUT_DIR / f"message-{case_id}-{run_id}.txt"
    message_path.write_text(str(case["user_input"]), encoding="utf-8")

    env = os.environ.copy()
    env["OPENCLAW_STATE_DIR"] = str(STATE_DIR)
    env["OPENCLAW_CONFIG_PATH"] = str(DEFAULT_CONFIG_PATH)
    env["OPENCLAW_LOG_LEVEL"] = "info"

    command = [
        "node",
        "openclaw.mjs",
        "agent",
        "--local",
        "--session-id",
        f"real-{case_id}-{run_id}",
        "--message-file",
        str(message_path),
        "--timeout",
        str(timeout),
        "--json",
    ]

    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(openclaw_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 4)

    stdout = completed.stdout or ""
    shield_decisions = parse_shield_blocks(stdout)
    plugin_logs = [
        line.strip()
        for line in (stdout + (completed.stderr or "")).splitlines()
        if "[GovAgentShield]" in line
    ]

    after_events = orchestrator.security_logger.get_recent_events(1000)
    audit_records = [e for e in after_events if e["id"] > before_max]
    audit_types = sorted(
        {str(e.get("event_type", "")) for e in audit_records if e.get("event_type")}
    )

    audit_decisions = [
        {
            "tool_name": e.get("tool_name"),
            "action": e.get("disposition"),
            "risk_score": e.get("risk_score"),
            "risk_level": e.get("risk_level"),
            "policy_id": e.get("policy_id"),
            "decision_reason": e.get("decision_reason"),
            "defense_stage": e.get("defense_stage"),
        }
        for e in audit_records
        if e.get("check_type") == "tool_call"
    ]
    audit_tool_calls = []
    for e in audit_records:
        if e.get("check_type") != "tool_call":
            continue
        try:
            params = json.loads(e.get("tool_params") or "{}")
        except (json.JSONDecodeError, TypeError):
            params = {}
        audit_tool_calls.append({
            "tool_name": e.get("tool_name"),
            "params": params,
        })

    decisions = shield_decisions or audit_decisions
    final_action = (
        str(decisions[-1].get("action", "")).lower()
        if decisions
        else "no_tool_call"
    )
    return {
        "case_id": case_id,
        "user_input": case.get("user_input"),
        "verification_mode": "real_openclaw",
        "real_command_succeeded": completed.returncode == 0,
        "command_returncode": completed.returncode,
        "agent_trace": plugin_logs,
        "tool_calls": audit_tool_calls or shield_decisions,
        "security_decisions": decisions,
        "risk_score": decisions[-1].get("risk_score")
        if decisions
        else None,
        "risk_level": decisions[-1].get("risk_level")
        if decisions
        else None,
        "final_action": final_action,
        "audit_events": audit_types,
        "audit_event_records": audit_records,
        "latency_ms": duration_ms,
    }


def run_simulated_case(
    client,
    orchestrator,
    case: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:
    """使用固定 Agent trace + TestClient 模拟 Plugin -> Engine 链路。"""
    case_id = str(case["case_id"])
    session_id = f"sim-{case_id}-{run_id}"
    orchestrator.start_session(session_id)

    input_context = None
    if case.get("document_context"):
        input_context = orchestrator.check_input(
            session_id,
            str(case.get("user_input", "")),
            context_text=case.get("document_context", ""),
        )

    pending_token = None
    agent_trace: List[Dict[str, Any]] = []
    security_decisions: List[Dict[str, Any]] = []
    latencies: List[float] = []
    final_action = "no_tool_call"

    for step_index, step in enumerate(
        case.get("expected_tool_plan", []),
        start=1,
    ):
        tool_name = str(step["tool_name"])
        params = copy.deepcopy(step.get("params", {}))
        if pending_token:
            params = replace_dpt_token(params, pending_token)

        request = {
            "session_id": session_id,
            "agent_id": "main",
            "tool_name": tool_name,
            "parameters": params,
            "context": {"run_id": session_id},
            "task_context": case.get("task_context", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        start = time.perf_counter()
        response = client.post("/security/check_tool", json=request)
        response.raise_for_status()
        decision = response.json()
        latency_ms = round((time.perf_counter() - start) * 1000, 4)
        latencies.append(latency_ms)

        security_decisions.append(decision)
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
        })

        if decision.get("inject_token") and pending_token is None:
            pending_token = decision["inject_token"]["token"]

        action = decision.get("action")
        if action in ("block", "kill"):
            final_action = action
            break
        if action == "review":
            if case.get("expected_result_type") in (
                "engine_review",
                "review_denied",
            ):
                final_action = "review"
                agent_trace[-1]["approval"] = "deny"
                break
            agent_trace[-1]["approval"] = "allow-once"
            continue
        final_action = action or "allow"

    events = orchestrator.security_logger.get_session_events(session_id)
    audit_types = sorted(
        {str(e.get("event_type", "")) for e in events if e.get("event_type")}
    )
    return {
        "case_id": case_id,
        "user_input": case.get("user_input"),
        "verification_mode": "simulated_testclient",
        "input_context": input_context,
        "agent_trace": agent_trace,
        "tool_calls": agent_trace,
        "security_decisions": security_decisions,
        "risk_score": security_decisions[-1].get("risk_score")
        if security_decisions
        else None,
        "risk_level": security_decisions[-1].get("risk_level")
        if security_decisions
        else None,
        "final_action": final_action,
        "audit_events": audit_types,
        "audit_event_records": events,
        "latency_ms": round(sum(latencies), 4),
    }


def write_outputs(results: List[Dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    with open(OUTPUT_DIR / "real_e2e_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_DIR / "agent_trace.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "case_id": r["case_id"],
                    "verification_mode": r["verification_mode"],
                    "agent_trace": r["agent_trace"],
                }
                for r in results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(OUTPUT_DIR / "audit_trace.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "case_id": r["case_id"],
                    "verification_mode": r["verification_mode"],
                    "audit_events": r["audit_events"],
                    "audit_event_records": r["audit_event_records"],
                }
                for r in results
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(OUTPUT_DIR / "e2e_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("Real OpenClaw E2E benchmark completed")
    for result in results:
        print(
            f"{result['case_id']} mode={result['verification_mode']} "
            f"action={result['final_action']} "
            f"latency_ms={result['latency_ms']}"
        )
    print(f"report={OUTPUT_DIR / 'real_e2e_report.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GovAgent-Shield real OpenClaw E2E benchmark"
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "real", "simulated"],
        default="auto",
    )
    parser.add_argument(
        "--openclaw-dir",
        type=Path,
        default=DEFAULT_OPENCLAW_DIR,
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    scenarios = load_scenarios()
    real_available = _is_real_available(args.openclaw_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.mode == "real" and not real_available:
        print("Real mode requested but OpenClaw environment unavailable")
        return 2

    client = TestClient(app)
    orchestrator = get_security_orchestrator()
    results: List[Dict[str, Any]] = []

    for case in scenarios:
        use_real = args.mode == "real" or (
            args.mode == "auto" and real_available
        )
        if use_real:
            try:
                result = run_real_case(
                    case,
                    args.openclaw_dir,
                    args.timeout,
                    run_id,
                )
                if (
                    args.mode == "auto"
                    and not result["real_command_succeeded"]
                ):
                    result = run_simulated_case(
                        client, orchestrator, case, run_id
                    )
            except Exception as exc:
                print(
                    f"Real OpenClaw case {case['case_id']} failed: {exc}"
                )
                if args.mode == "real":
                    raise
                result = run_simulated_case(
                    client, orchestrator, case, run_id
                )
        else:
            result = run_simulated_case(
                client, orchestrator, case, run_id
            )
        results.append(result)

    write_outputs(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
