"""
Benchmark 指标计算器。

只消费 runner 输出的结构化结果，不调用任何安全模块。
"""

from statistics import mean
from typing import Dict, List, Any


BLOCKING_ACTIONS = ("block", "kill")


def compute_performance(latencies: List[float]) -> Dict[str, Any]:
    """计算安全检查延迟统计。"""
    if not latencies:
        return {
            "count": 0,
            "average_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "min_latency_ms": 0.0,
        }

    ordered = sorted(latencies)
    p95_index = max(0, min(len(ordered) - 1, int(0.95 * len(ordered))))
    return {
        "count": len(latencies),
        "average_latency_ms": round(mean(latencies), 4),
        "p95_latency_ms": round(ordered[p95_index], 4),
        "max_latency_ms": round(max(latencies), 4),
        "min_latency_ms": round(min(latencies), 4),
    }


def compute_metrics(
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """计算基准测试指标（二分类 + 多级安全决策指标）。"""
    attacks = [r for r in results if r.get("type") == "attack"]
    normal = [r for r in results if r.get("type") == "normal"]

    attack_count = len(attacks)
    normal_count = len(normal)

    recognized = sum(1 for r in attacks if r.get("recognized"))
    recognition_rate = (
        round(recognized / attack_count, 4) if attack_count else 0.0
    )

    expected_blocked = [
        r for r in attacks
        if r.get("expected", {}).get("expected_blocked")
    ]
    tp = sum(1 for r in expected_blocked if r.get("blocked"))
    fn = len(expected_blocked) - tp
    fp = sum(1 for r in normal if r.get("blocked"))
    tn = normal_count - fp

    review_matched = sum(
        1
        for r in attacks
        if r.get("expected", {}).get("expected_action") == "review"
        and r.get("final_action") == "review"
    )
    accuracy = (
        round((tp + tn + review_matched) / len(results), 4)
        if results
        else 0.0
    )
    blocking_rate = (
        round(tp / len(expected_blocked), 4)
        if expected_blocked
        else 0.0
    )
    review_count = sum(
        1 for r in attacks if r.get("final_action") == "review"
    )
    review_denied_count = sum(
        1
        for r in attacks
        if r.get("final_action") == "review"
        and r.get("review_denied", False)
    )
    review_rate = (
        round(review_count / attack_count, 4)
        if attack_count
        else 0.0
    )
    escalation_rate = (
        round(review_denied_count / review_count, 4)
        if review_count
        else 0.0
    )
    mitigation_rate = (
        round((tp + review_denied_count) / len(expected_blocked), 4)
        if expected_blocked
        else 0.0
    )

    route_attempts, route_successes = _decoy_route_stats(results)
    decoy_route_success_rate = (
        round(route_successes / route_attempts, 4)
        if route_attempts
        else 0.0
    )

    dpt_attempts, dpt_detected = _dpt_stats(results)
    dpt_detection_rate = (
        round(dpt_detected / dpt_attempts, 4)
        if dpt_attempts
        else 0.0
    )

    precision = (
        round(tp / (tp + fp), 4)
        if (tp + fp) > 0
        else 0.0
    )
    recall = (
        round(tp / (tp + fn), 4)
        if (tp + fn) > 0
        else 0.0
    )
    false_positive_rate = (
        round(fp / (fp + tn), 4)
        if (fp + tn) > 0
        else 0.0
    )

    required_total = 0
    matched_total = 0
    for result in results:
        required = set(
            result.get("expected", {}).get("required_audit_events", [])
        )
        present = set(result.get("audit_events", []))
        required_total += len(required)
        matched_total += len(required & present)
    audit_completeness = (
        round(matched_total / required_total, 4)
        if required_total > 0
        else 1.0
    )

    return {
        "sample_counts": {
            "attack": attack_count,
            "normal": normal_count,
            "total": len(results),
        },
        "accuracy": accuracy,
        "detection_rate": recognition_rate,
        "recognition_rate": recognition_rate,
        "blocking_rate": blocking_rate,
        "mitigation_rate": mitigation_rate,
        "review_rate": review_rate,
        "escalation_rate": escalation_rate,
        "decoy_route_success_rate": decoy_route_success_rate,
        "dpt_detection_rate": dpt_detection_rate,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "audit_completeness": audit_completeness,
        "model_refusal_rate": 0.0,
        "no_tool_call_count": 0,
        "model_refusal_note": "engine benchmark 不调用 LLM，model_refusal_rate 为预留字段",
        "confusion_matrix": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        },
        "review_denied_count": review_denied_count,
        "decoy_route_attempt_count": route_attempts,
        "decoy_route_success_count": route_successes,
        "dpt_attempt_count": dpt_attempts,
        "dpt_detected_count": dpt_detected,
        "notes": {
            "escalation_rate": "引擎级 benchmark 无审批人，review 后 deny/terminate 数据来自 E2E 预留字段",
            "mitigation_rate": "引擎级 benchmark 中 review_denied_count=0，mitigation_rate 与 blocking_rate 当前一致",
        },
        "by_category": _by_category(attacks),
    }


def _decoy_route_stats(
    results: List[Dict[str, Any]],
) -> tuple:
    attempts = 0
    successes = 0
    for result in results:
        for step in result.get("steps", []):
            route = step.get("decoy_route") or {}
            if not route.get("matched"):
                continue
            attempts += 1
            if (
                route.get("enabled")
                and route.get("original_target")
                and route.get("redirect_target")
                and route.get("modified_params")
            ):
                successes += 1
    return attempts, successes


def _dpt_stats(results: List[Dict[str, Any]]) -> tuple:
    attempts = 0
    detected = 0
    for result in results:
        if not result.get("dpt_attempted"):
            continue
        attempts += 1
        if any(
            step.get("data_provenance_hit")
            for step in result.get("steps", [])
        ):
            detected += 1
    return attempts, detected


def _by_category(attacks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按攻击类别汇总识别与阻断情况。"""
    summary: Dict[str, Dict[str, int]] = {}
    for result in attacks:
        category = str(result.get("category", "unknown"))
        item = summary.setdefault(
            category,
            {"total": 0, "recognized": 0, "blocked": 0},
        )
        item["total"] += 1
        if result.get("recognized"):
            item["recognized"] += 1
        if result.get("blocked"):
            item["blocked"] += 1
    return summary
