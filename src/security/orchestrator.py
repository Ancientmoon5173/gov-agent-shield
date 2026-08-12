"""
安全协调器（SecurityOrchestrator）。

安全层对外的唯一接口。Agent 只调用三个方法：
- check_input()     --> 输入注入检测
- check_tool_call() --> 工具调用检测（参数 + 行为链 + 诱饵）
- check_output()    --> 输出敏感数据检测

内部协调 8 个模块：InputDetector, ParameterChecker, BehaviorAnalyzer,
DecoyManager, PermissionChecker, OutputGuard, RiskScorer,
DispositionEngine, SecurityLogger
"""

from typing import Dict, Any, Optional

from src.input_guard import InputDetector
from src.input_guard.rules import get_default_detector
from src.tool_gateway import ToolGateway
from src.tool_gateway.policies import get_default_gateway
from src.risk_engine import RiskScorer, DispositionEngine
from src.risk_engine.actions import PASSING_ACTIONS, BLOCKING_ACTIONS
from src.config import (
    RISK_THRESHOLD_LOW,
    RISK_THRESHOLD_MEDIUM,
    RISK_THRESHOLD_HIGH,
    PERMISSION_FORCE_BLOCK,
)

from .tool_risk_config import TOOL_RISK_CONFIG
from .parameter_checker import ParameterChecker, create_parameter_checker
from .behavior_analyzer import BehaviorAnalyzer, create_behavior_analyzer
from .output_guard import OutputGuard, create_output_guard
from .security_logger import SecurityLogger, create_security_logger
from .permission_checker import PermissionChecker, create_permission_checker
from .decoy_manager import DecoyManager, create_decoy_manager
from .data_classifier import DataClassifier, create_data_classifier
from .asset_resolver import AssetResolver, create_asset_resolver
from .behavior_observer import BehaviorObserver, create_behavior_observer
from .data_provenance import (
    DataProvenanceTracker,
    create_data_provenance_tracker,
)
from .decoy_copy_generator import create_decoy_copy_generator
from src.input_guard.sensitive_data_leak_detector import SensitiveDataLeakDetector
from src.input_guard.input_risk_context import (
    InputRiskContext,
    create_input_risk_context_store,
)


# 五维风险融合权重
RISK_WEIGHTS = {
    "R_input": 0.15,
    "R_tool": 0.25,
    "R_output": 0.15,
    "R_behavior": 0.15,
    "R_decoy": 0.30,
}


def _calculate_final_risk(
    r_input: float,
    r_tool: float,
    r_output: float,
    r_behavior: float,
    r_decoy: float = 0.0,
) -> Dict[str, Any]:
    """
    五维风险融合算法。
    BaseRisk = weighted average
    FinalRisk = max(BaseRisk, MaxRisk * 0.85)
    """
    scores = {
        "R_input": round(r_input, 3),
        "R_tool": round(r_tool, 3),
        "R_output": round(r_output, 3),
        "R_behavior": round(r_behavior, 3),
        "R_decoy": round(r_decoy, 3),
    }

    weighted_sum = (
        r_input * RISK_WEIGHTS["R_input"]
        + r_tool * RISK_WEIGHTS["R_tool"]
        + r_output * RISK_WEIGHTS["R_output"]
        + r_behavior * RISK_WEIGHTS["R_behavior"]
        + r_decoy * RISK_WEIGHTS["R_decoy"]
    )
    total_weight = sum(RISK_WEIGHTS.values())
    base_risk = weighted_sum / total_weight if total_weight > 0 else 0
    max_risk = max(r_input, r_tool, r_output, r_behavior, r_decoy)

    final_risk = max(base_risk, max_risk * 0.85)

    if final_risk >= 0.85:
        level = "CRITICAL"
    elif final_risk >= 0.70:
        level = "VERY_HIGH"
    elif final_risk >= 0.50:
        level = "HIGH"
    elif final_risk >= 0.30:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "total_score": round(final_risk, 3),
        "base_score": round(base_risk, 3),
        "max_score": round(max_risk, 3),
        "level": level,
        "dimensions": scores,
    }


class SecurityOrchestrator:
    """
    安全协调器。管理所有安全模块的调用链。
    """

    def __init__(
        self,
        input_detector: InputDetector = None,
        tool_gateway: ToolGateway = None,
        parameter_checker: ParameterChecker = None,
        behavior_analyzer: BehaviorAnalyzer = None,
        output_guard: OutputGuard = None,
        permission_checker: PermissionChecker = None,
        decoy_manager: DecoyManager = None,
        security_logger: SecurityLogger = None,
        data_classifier: DataClassifier = None,
        asset_resolver: AssetResolver = None,
        behavior_observer: BehaviorObserver = None,
        data_provenance_tracker: DataProvenanceTracker = None,
    ):
        self.input_detector = input_detector or get_default_detector()
        self.tool_gateway = tool_gateway or get_default_gateway()
        self.parameter_checker = parameter_checker or create_parameter_checker()
        self.behavior_analyzer = behavior_analyzer or create_behavior_analyzer()
        self.output_guard = output_guard or create_output_guard()
        self.permission_checker = permission_checker or create_permission_checker()
        self.decoy_manager = decoy_manager or create_decoy_manager()
        self.security_logger = security_logger or create_security_logger()
        self.data_classifier = data_classifier or create_data_classifier()
        self.asset_resolver = asset_resolver or create_asset_resolver()
        self.behavior_observer = behavior_observer or create_behavior_observer()
        self.data_provenance_tracker = (
            data_provenance_tracker or create_data_provenance_tracker()
        )
        # 诱饵副本预埋的令牌必须进入同一注册表，才能被外发扫描命中
        self.decoy_manager.copy_generator = create_decoy_copy_generator(
            tracker=self.data_provenance_tracker
        )
        self.sensitive_data_leak_detector = SensitiveDataLeakDetector()
        self._asset_hit_count: Dict[str, int] = {}
        self.input_risk_store = create_input_risk_context_store()

        self.disposition_engine = DispositionEngine()

    def check_input(self, session_id: str, user_input: str,
                    context_text: str = "") -> Dict[str, Any]:
        """
        检查用户输入安全性，并生成 Input Risk Context。

        Args:
            session_id: 会话 ID
            user_input: 用户输入
            context_text: 可选上下文文本（知识库/文档内容污染检测）
        """
        scan_result = self.input_detector.scan(user_input)
        leak_result = self.sensitive_data_leak_detector.scan(user_input)
        if leak_result["risk_score"] > scan_result.get("risk_score", 0):
            scan_result["risk_score"] = leak_result["risk_score"]
        if leak_result.get("findings"):
            for f in leak_result["findings"]:
                scan_result["findings"].append(f)
        r_input = scan_result.get("risk_score", 0.0)

        # 输入风险上下文（Runtime Risk Context）
        context_source = "user_input"
        if context_text:
            ctx_scan = self.input_detector.scan(context_text)
            ctx_leak = self.sensitive_data_leak_detector.scan(context_text)
            if ctx_scan.get("findings") or ctx_leak.get("findings"):
                context_source = "document_context"
            for ctx_f in ctx_scan.get("findings", []) + ctx_leak.get("findings", []):
                scan_result.setdefault("findings", []).append(ctx_f)
            ctx_risk = max(
                ctx_scan.get("risk_score", 0.0),
                ctx_leak.get("risk_score", 0.0),
            )
            r_input = max(r_input, ctx_risk)
            scan_result["risk_score"] = r_input

        risk_type = self._derive_input_risk_type(
            findings=scan_result.get("findings", []),
            has_context=bool(context_text),
        )
        self.input_risk_store.set(
            session_id,
            InputRiskContext(
                source=context_source,
                risk_type=risk_type,
                risk_score=r_input,
                findings=[
                    f.get("detail", f.get("rule_name", ""))
                    for f in scan_result.get("findings", [])
                ],
            ),
        )

        risk = _calculate_final_risk(
            r_input=r_input, r_tool=0.0, r_output=0.0,
            r_behavior=0.0, r_decoy=0.0,
        )

        disposition = self._map_disposition(risk["total_score"], risk["level"])
        passed = disposition["action"] in PASSING_ACTIONS

        # 审计：事件类型推导
        findings_types = {
            f.get("type") for f in scan_result.get("findings", [])
        }
        if "data_exfiltration" in findings_types:
            event_type = "data_exfiltration"
        elif findings_types & {"jailbreak", "command_override", "prompt_injection"}:
            event_type = "prompt_injection"
        else:
            event_type = "input_risk"

        self.security_logger.log_check(
            session_id=session_id, check_type="input",
            input_text=user_input, risk_score=risk["total_score"],
            risk_level=risk["level"], disposition=disposition["action"],
            details={"dimensions": risk["dimensions"], "findings": scan_result.get("findings", [])},
            event_type=event_type,
            decision_reason=disposition.get("reason", ""),
            defense_stage="input_guard",
        )

        return {
            "passed": passed,
            "risk_score": risk["total_score"],
            "risk_level": risk["level"],
            "action": disposition["action"],
            "action_name": disposition["action_name"],
            "reason": disposition["reason"],
            "findings": scan_result.get("findings", []),
        }

    def check_tool_call(
        self,
        session_id: str,
        tool_name: str,
        params: Dict[str, Any],
        user_input: str = "",
        agent_id: str = "default_agent",
    ) -> Dict[str, Any]:
        """
        检查工具调用安全性（核心检测点）。

        检测链路：
        ParameterChecker --> BehaviorAnalyzer --> DecoyManager
        --> PermissionChecker --> RiskScorer --> DispositionEngine
        """
        tool_config = TOOL_RISK_CONFIG.get(tool_name, {})
        r_tool_base = tool_config.get("base_risk", 0.5)

        # 1. 参数风险
        param_result = self.parameter_checker.check(tool_name, params)
        r_tool = min(r_tool_base + param_result["risk_score"], 1.0)

        # 1.1 数据分级（作为 tool risk 修正因素，不新增风险维度）
        data_result = self.data_classifier.classify(tool_name, params)
        data_context = {
            "data_class": data_result["data_class"],
            "data_findings": data_result["findings"],
        }
        r_tool = max(r_tool, data_result["risk_score"])

        # 1.2 资产身份识别（AssetResolver）
        asset_context = self.asset_resolver.resolve(tool_name, params)
        if asset_context.get("matched"):
            self.security_logger.log_check(
                session_id=session_id, check_type="asset_resolved",
                tool_name=tool_name, tool_params=params,
                risk_score=0.0, risk_level="LOW",
                disposition="detected",
                details=asset_context,
                event_type="asset_resolved",
                defense_stage="asset_resolver",
            )
            self._asset_hit_count[session_id] = (
                self._asset_hit_count.get(session_id, 0) + 1
            )

        # 2. 行为链风险
        self.behavior_analyzer.record_call(session_id, tool_name, params)
        behavior_result = self.behavior_analyzer.analyze(session_id)

        # 2.1 行为特征观察（方案 B，低权重，不阻断）
        observer_result = self.behavior_observer.observe(
            tool_name=tool_name,
            params=params,
            asset_context=asset_context,
            prior_hits=max(self._asset_hit_count.get(session_id, 0) - 1, 0),
        )
        if observer_result.get("virtual_hit"):
            behavior_result["behavior_score"] = min(
                behavior_result["behavior_score"]
                + float(observer_result.get("risk_increment", 0.0)),
                1.0,
            )
            self.security_logger.log_check(
                session_id=session_id, check_type="decoy_virtual_hit",
                tool_name=tool_name, tool_params=params,
                risk_score=float(observer_result.get("risk_increment", 0.0)),
                risk_level="LOW",
                disposition="observed",
                details={
                    "rule_id": observer_result.get("rule_id", ""),
                    "confidence": observer_result.get("confidence", 0.0),
                    "risk_increment": observer_result.get("risk_increment", 0.0),
                    "asset": asset_context,
                },
                event_type="decoy_virtual_hit",
                defense_stage="behavior_observer",
            )

        # 3. 动态诱捕检测（新增）
        decoy_result = self.decoy_manager.check_access(tool_name, params)
        r_decoy = decoy_result.get("risk_score", 0.0)

        # 构建 decoy_context 供 DispositionEngine 决策
        has_upload = "upload_data" in [
            c["tool"] for c in self.behavior_analyzer._history.get(session_id, [])
        ]
        decoy_context = {
            "triggered": decoy_result.get("triggered", False),
            "risk_score": r_decoy,
            "decoy_type": decoy_result.get("decoy_type", ""),
            "resource": decoy_result.get("resource", ""),
            "detail": decoy_result.get("detail", ""),
            "has_upload_context": has_upload,
            "is_authorized": False,
        }

        # 3.1 Shadow Decoy 路由建议（方案 A）：读取/搜索类 + 敏感资产 + 高风险会话
        route_context = self.decoy_manager.build_route(
            session_id=session_id,
            tool_name=tool_name,
            params=params,
            asset_context=asset_context,
            risk_score=max(
                r_tool,
                behavior_result["behavior_score"],
                r_decoy,
            ),
        )

        # 3.2 数据溯源令牌泄漏扫描（方案 C 第一阶段：外发/写入参数扫描）
        dpt_result = self.data_provenance_tracker.scan_leak(tool_name, params)
        if dpt_result.get("hit"):
            self.security_logger.log_check(
                session_id=session_id, check_type="data_provenance_leak",
                tool_name=tool_name, tool_params=params,
                risk_score=1.0, risk_level="CRITICAL", disposition="block",
                details={
                    "token": dpt_result.get("token", ""),
                    "token_info": dpt_result.get("token_info", {}),
                    "asset": asset_context,
                },
                event_type="data_provenance_leak_detected",
                policy_id="data_provenance:leak",
                decision_reason="检测到数据溯源令牌外泄，阻断外发",
                defense_stage="data_provenance",
                chain_summary=self._build_chain_summary(session_id),
            )
            return {
                "blocked": True,
                "risk_score": 1.0,
                "risk_level": "CRITICAL",
                "action": "block",
                "action_name": "阻断",
                "reason": "检测到数据溯源令牌外泄，已阻断外发",
                "policy_id": "data_provenance:leak",
                "defense_stage": "data_provenance",
                "decision_reason": "检测到数据溯源令牌外泄，阻断外发",
                "data_provenance": dpt_result,
                "asset": asset_context,
            }

        # 4. 记录诱饵事件到 BehaviorAnalyzer
        if decoy_result.get("triggered"):
            behavior_event = {
                "event": "decoy_access",
                "severity": "critical",
                "resource": decoy_result.get("resource", ""),
            }
            self.security_logger.log_check(
                session_id=session_id, check_type="decoy_event",
                tool_name=tool_name, tool_params=params,
                risk_score=1.0, risk_level="CRITICAL",
                disposition="detected",
                details=behavior_event,
                event_type="tool_risk",
                defense_stage="decoy_manager",
            )

        # 5. 权限检查（策略提供器）
        perm_result = self.permission_checker.check(agent_id, tool_name, params)
        perm_action = perm_result.action
        perm_policy = (
            self.permission_checker.to_policy_dict(agent_id)
            if hasattr(self.permission_checker, "to_policy_dict")
            else {}
        )

        if PERMISSION_FORCE_BLOCK:
            # 兼容模式：权限层直接阻断/审批（保持原行为）
            if perm_action == "block":
                self.security_logger.log_check(
                    session_id=session_id, check_type="permission",
                    tool_name=tool_name, tool_params=params,
                    risk_score=1.0, risk_level="VERY_HIGH", disposition="block",
                    details={"reason": perm_result.reason, "policy": perm_policy},
                    event_type="permission_violation",
                    policy_id="permission:block",
                    decision_reason=perm_result.reason,
                    defense_stage="permission_checker",
                    chain_summary=self._build_chain_summary(session_id),
                )
                return {
                    "blocked": True, "risk_score": 1.0, "risk_level": "VERY_HIGH",
                    "action": "block", "action_name": "阻断",
                    "reason": perm_result.reason,
                    "policy_id": "permission:block",
                    "dimensions": {"R_permission": 1.0}, "param_findings": [],
                    "behavior": behavior_result,
                    "decoy": decoy_result,
                    "permission_policy": perm_policy,
                    "defense_stage": "permission_checker",
                    "decision_reason": perm_result.reason,
                }

            if perm_action == "review":
                self.security_logger.log_check(
                    session_id=session_id, check_type="permission",
                    tool_name=tool_name, tool_params=params,
                    risk_score=0.7, risk_level="HIGH", disposition="review",
                    details={
                        "approval_id": perm_result.approval_id,
                        "reason": perm_result.reason,
                        "policy": perm_policy,
                    },
                    event_type="permission_violation",
                    policy_id="permission:review",
                    decision_reason=perm_result.reason,
                    defense_stage="permission_checker",
                    chain_summary=self._build_chain_summary(session_id),
                )
                return {
                    "blocked": False, "risk_score": 0.7, "risk_level": "HIGH",
                    "action": "review", "action_name": "审批",
                    "reason": perm_result.reason,
                    "policy_id": "permission:review",
                    "dimensions": {"R_permission": 0.7}, "param_findings": [],
                    "behavior": behavior_result,
                    "decoy": decoy_result,
                    "approval_id": perm_result.approval_id,
                    "permission_policy": perm_policy,
                    "defense_stage": "permission_checker",
                    "decision_reason": perm_result.reason,
                }

            r_permission = 0.0
            perm_context = {
                "action": "allow",
                "policy": perm_policy,
                "R_permission": 0.0,
            }
        else:
            # 信号化模式：权限结果转为风险维度，由 DispositionEngine 统一决策
            r_permission = {"block": 0.9, "review": 0.6}.get(perm_action, 0.0)
            r_tool = max(r_tool, r_permission)
            perm_context = {
                "action": perm_action,
                "policy": perm_policy,
                "R_permission": r_permission,
            }
            self.security_logger.log_check(
                session_id=session_id, check_type="permission_signal",
                tool_name=tool_name, tool_params=params,
                risk_score=r_permission,
                risk_level="HIGH" if r_permission >= 0.6 else "LOW",
                disposition=perm_action,
                details=perm_context,
                event_type=(
                    "permission_violation"
                    if perm_action in ("block", "review")
                    else "tool_risk"
                ),
                policy_id="permission:signal",
                decision_reason=perm_result.reason,
                defense_stage="permission_checker",
                chain_summary=self._build_chain_summary(session_id),
            )

        # 5.1 权限通过后：decoy_route 命中 → 审计（dry-run 同样记录，便于调参）
        if route_context.get("deployment_missing"):
            self.security_logger.log_check(
                session_id=session_id, check_type="decoy_deployment_missing",
                tool_name=tool_name, tool_params=params,
                risk_score=max(
                    r_tool, behavior_result["behavior_score"], r_decoy
                ),
                risk_level="VERY_HIGH",
                disposition="reroute_failed",
                details={
                    "reason": route_context.get("deployment_reason", ""),
                    "asset": asset_context,
                },
                event_type="decoy.deployment_missing",
                policy_id="decoy:deployment_missing",
                decision_reason=route_context.get("deployment_reason", ""),
                defense_stage="decoy_copy_generator",
                chain_summary=self._build_chain_summary(session_id),
            )
        elif route_context.get("matched"):
            self.security_logger.log_check(
                session_id=session_id, check_type="decoy_route_triggered",
                tool_name=tool_name, tool_params=params,
                risk_score=max(
                    r_tool, behavior_result["behavior_score"], r_decoy
                ),
                risk_level="VERY_HIGH",
                disposition="rerouted",
                details={
                    "original_target": route_context.get("original_target", ""),
                    "redirect_target": route_context.get("redirect_target", ""),
                    "reason": route_context.get("reason", ""),
                    "policy_id": route_context.get("policy_id", ""),
                    "dry_run": route_context.get("dry_run", True),
                    "enabled": route_context.get("enabled", False),
                    "asset": asset_context,
                },
                event_type="decoy_route_triggered",
                policy_id=route_context.get("policy_id", ""),
                decision_reason=route_context.get("reason", ""),
                defense_stage="decoy_manager",
                chain_summary=self._build_chain_summary(session_id),
            )
            if route_context.get("token"):
                self.security_logger.log_check(
                    session_id=session_id,
                    check_type="data_provenance_injected",
                    tool_name=tool_name, tool_params=params,
                    risk_score=max(
                        r_tool, behavior_result["behavior_score"], r_decoy
                    ),
                    risk_level="MEDIUM",
                    disposition="injected",
                    details={
                        "token": route_context.get("token", ""),
                        "copy_path": route_context.get("redirect_target", ""),
                        "policy_id": route_context.get("policy_id", ""),
                        "asset": asset_context,
                    },
                    event_type="data_provenance_injected",
                    policy_id=route_context.get("policy_id", ""),
                    decision_reason="诱饵副本预埋数据溯源令牌",
                    defense_stage="decoy_copy_generator",
                    chain_summary=self._build_chain_summary(session_id),
                )

        # 6. 综合评分（权限通过后）
        input_context = self.input_risk_store.get(session_id)
        r_input = input_context.boost() if input_context.risk_score > 0 else 0.0
        risk = _calculate_final_risk(
            r_input=r_input,
            r_tool=r_tool,
            r_output=0.0,
            r_behavior=behavior_result["behavior_score"],
            r_decoy=r_decoy,
        )

        # 7. 处置决策（传入 decoy_context 给 DecoyTriggered 策略）
        disposition = self.disposition_engine.decide(risk, decoy_context)
        blocked = disposition["action"] in BLOCKING_ACTIONS

        # 7.1 普通敏感读取：返回结果级令牌注入指令（方案 C-2b）
        inject_token = None
        route_enabled = route_context.get("matched") and route_context.get(
            "enabled"
        )
        if (
            self.data_provenance_tracker.should_inject(tool_name)
            and data_context["data_class"] in ("SENSITIVE", "CRITICAL")
            and not decoy_result.get("triggered")
            and not route_enabled
            and not blocked
        ):
            token = self.data_provenance_tracker.generate_token()
            self.data_provenance_tracker.register(
                session_id,
                "",
                token,
                metadata={
                    "source": "tool_result_inject",
                    "tool_name": tool_name,
                    "data_class": data_context["data_class"],
                },
            )
            inject_token = {
                "token": token,
                "policy_id": (
                    f"data_provenance:inject:"
                    f"{data_context['data_class'].lower()}"
                ),
                "inject_mode": self.data_provenance_tracker.inject_mode(),
                "target_param": "file_path",
            }

        # Determine defense_stage
        if decoy_result.get("triggered"):
            defense_stage = "decoy_manager"
        elif param_result.get("findings"):
            defense_stage = "parameter_checker"
        elif behavior_result["behavior_score"] > 0:
            defense_stage = "behavior_analyzer"
        else:
            defense_stage = "risk_engine"

        # 审计：事件类型推导
        event_type = self._resolve_event_type(
            tool_name=tool_name,
            data_class=data_context["data_class"],
            behavior_score=behavior_result["behavior_score"],
            decoy_triggered=decoy_result.get("triggered", False),
            perm_action=perm_action,
        )

        # 8. 日志记录
        self.security_logger.log_check(
            session_id=session_id, check_type="tool_call",
            tool_name=tool_name, tool_params=params,
            risk_score=risk["total_score"],
            risk_level=risk["level"],
            disposition=disposition["action"],
            details={
                "dimensions": risk["dimensions"],
                "param_findings": param_result.get("findings", []),
                "behavior": behavior_result,
                "decoy": decoy_result,
                "disposition": disposition,
                "permission": perm_context,
                "data": data_context,
                "input_context": input_context.to_dict(),
                "asset": asset_context,
                "behavior_observer": observer_result,
                "decoy_route": route_context,
                "data_provenance": dpt_result,
                "inject_token": inject_token,
            },
            event_type=event_type,
            policy_id=disposition.get("policy_id", ""),
            decision_reason=disposition.get("reason", ""),
            defense_stage=defense_stage,
            chain_summary=self._build_chain_summary(session_id),
        )

        return {
            "blocked": blocked,
            "defense_stage": defense_stage,
            "decision_reason": disposition.get("reason", ""),
            "risk_score": risk["total_score"],
            "risk_level": risk["level"],
            "action": disposition["action"],
            "action_name": disposition["action_name"],
            "reason": disposition["reason"],
            "policy_id": disposition.get("policy_id", "disposition:unknown"),
            "dimensions": risk["dimensions"],
            "param_findings": param_result.get("findings", []),
            "behavior": behavior_result,
            "decoy": decoy_result,
            "data_class": data_context["data_class"],
            "data_findings": data_context["data_findings"],
            "asset": asset_context,
            "permission_policy": perm_policy,
            "decoy_route": route_context,
            "data_provenance": dpt_result,
            "inject_token": inject_token,
        }

    def check_output(self, session_id: str, tool_name: str,
                     output_text: str) -> Dict[str, Any]:
        """检查工具输出是否包含敏感数据。"""
        scan_result = self.output_guard.scan(output_text)

        if scan_result["has_sensitive_data"]:
            masked = self.output_guard.mask_sensitive(output_text)
            risk = _calculate_final_risk(
                r_input=0.0, r_tool=0.0, r_output=scan_result["risk_score"],
                r_behavior=0.0, r_decoy=0.0,
            )
            disposition = self._map_disposition(risk["total_score"], risk["level"])
            self.security_logger.log_check(
                session_id=session_id, check_type="output",
                tool_name=tool_name, risk_score=risk["total_score"],
                risk_level=risk["level"], disposition="masked",
                details={"findings": scan_result["findings"]},
            )
            return {
                "has_sensitive_data": True,
                "risk_score": risk["total_score"],
                "risk_level": risk["level"],
                "action": "masked",
                "policy_id": "output:masked",
                "findings": scan_result["findings"],
                "masked_output": masked,
            }

        return {
            "has_sensitive_data": False,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "action": "allow",
            "policy_id": "output:allow",
            "findings": [],
            "masked_output": output_text,
        }

    def _map_disposition(self, score: float, level: str) -> Dict[str, str]:
        """兼容辅助：委托给 DispositionEngine，保证 action 唯一来源。"""
        risk = {"total_score": score, "level": level}
        return self.disposition_engine.decide(risk)

    def _resolve_event_type(
        self,
        tool_name: str,
        data_class: str,
        behavior_score: float,
        decoy_triggered: bool,
        perm_action: str,
    ) -> str:
        """根据风险结果推导审计事件类型。"""
        if perm_action == "block":
            return "permission_violation"
        if decoy_triggered:
            return "tool_risk"
        if behavior_score > 0:
            return "behavior_chain"
        if data_class in ("SENSITIVE", "CRITICAL") and tool_name == "upload_data":
            return "data_exfiltration"
        return "tool_risk"

    def _build_chain_summary(self, session_id: str) -> str:
        """从行为历史生成工具调用链摘要。"""
        history = self.behavior_analyzer._history.get(session_id, [])
        return " -> ".join(c["tool"] for c in history[-5:])

    def _derive_input_risk_type(
        self,
        findings: list,
        has_context: bool = False,
    ) -> str:
        """根据输入检测 findings 推导 Input Risk Context 风险类型。"""
        finding_types = {f.get("type") for f in findings}
        if "jailbreak" in finding_types:
            return "jailbreak"
        if finding_types & {"command_override", "prompt_injection"}:
            return "prompt_injection"
        if finding_types & {"data_exfiltration", "sensitive_request"}:
            return "sensitive_instruction"
        if has_context:
            return "data_poisoning"
        return "input_risk"

    def start_session(self, session_id: str) -> None:
        """初始化一个新会话。"""
        self.behavior_analyzer.reset_session(session_id)

    def get_security_summary(self) -> Dict[str, Any]:
        """获取安全事件摘要。"""
        return self.security_logger.get_summary()

    def get_session_events(self, session_id: str) -> list:
        """获取指定会话的安全事件。"""
        return self.security_logger.get_session_events(session_id)


def create_orchestrator() -> SecurityOrchestrator:
    """创建安全协调器实例。"""
    return SecurityOrchestrator()
