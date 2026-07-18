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
from src.config import RISK_THRESHOLD_LOW, RISK_THRESHOLD_MEDIUM, RISK_THRESHOLD_HIGH

from .tool_risk_config import TOOL_RISK_CONFIG
from .parameter_checker import ParameterChecker, create_parameter_checker
from .behavior_analyzer import BehaviorAnalyzer, create_behavior_analyzer
from .output_guard import OutputGuard, create_output_guard
from .security_logger import SecurityLogger, create_security_logger
from .permission_checker import PermissionChecker, create_permission_checker
from .decoy_manager import DecoyManager, create_decoy_manager


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
    ):
        self.input_detector = input_detector or get_default_detector()
        self.tool_gateway = tool_gateway or get_default_gateway()
        self.parameter_checker = parameter_checker or create_parameter_checker()
        self.behavior_analyzer = behavior_analyzer or create_behavior_analyzer()
        self.output_guard = output_guard or create_output_guard()
        self.permission_checker = permission_checker or create_permission_checker()
        self.decoy_manager = decoy_manager or create_decoy_manager()
        self.security_logger = security_logger or create_security_logger()

        self.disposition_engine = DispositionEngine()

    def check_input(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """检查用户输入安全性。"""
        scan_result = self.input_detector.scan(user_input)
        r_input = scan_result.get("risk_score", 0.0)

        risk = _calculate_final_risk(
            r_input=r_input, r_tool=0.0, r_output=0.0,
            r_behavior=0.0, r_decoy=0.0,
        )

        disposition = self._map_disposition(risk["total_score"], risk["level"])
        passed = disposition["action"] in ("allow", "review", "warn")

        self.security_logger.log_check(
            session_id=session_id, check_type="input",
            input_text=user_input, risk_score=risk["total_score"],
            risk_level=risk["level"], disposition=disposition["action"],
            details={"dimensions": risk["dimensions"], "findings": scan_result.get("findings", [])},
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

        # 2. 行为链风险
        self.behavior_analyzer.record_call(session_id, tool_name, params)
        behavior_result = self.behavior_analyzer.analyze(session_id)

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
            )

        # 5. 权限风险（MVP 返回 0）
        r_permission = self.permission_checker.calculate_permission_risk()

        # 6. 综合评分
        risk = _calculate_final_risk(
            r_input=0.0,
            r_tool=r_tool,
            r_output=0.0,
            r_behavior=behavior_result["behavior_score"],
            r_decoy=r_decoy,
        )

        # 7. 处置决策（传入 decoy_context 给 DecoyTriggered 策略）
        disposition = self.disposition_engine.decide(risk, decoy_context)
        blocked = disposition["action"] in ("block", "kill")

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
            },
        )

        return {
            "blocked": blocked,
            "risk_score": risk["total_score"],
            "risk_level": risk["level"],
            "action": disposition["action"],
            "action_name": disposition["action_name"],
            "reason": disposition["reason"],
            "dimensions": risk["dimensions"],
            "param_findings": param_result.get("findings", []),
            "behavior": behavior_result,
            "decoy": decoy_result,
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
                "findings": scan_result["findings"],
                "masked_output": masked,
            }

        return {
            "has_sensitive_data": False,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "action": "allow",
            "findings": [],
            "masked_output": output_text,
        }

    def _map_disposition(self, score: float, level: str) -> Dict[str, str]:
        """常规 5 级映射（不含 DecoyTriggered 策略）。"""
        if level == "CRITICAL":
            return {"action": "kill", "action_name": "熔断", "reason": "检测到严重安全攻击，已终止任务"}
        elif level == "VERY_HIGH":
            return {"action": "block", "action_name": "阻断", "reason": "检测到高风险操作，已阻断"}
        elif level == "HIGH":
            return {"action": "review", "action_name": "审批", "reason": "检测到可疑行为，需要人工确认"}
        elif level == "MEDIUM":
            return {"action": "warn", "action_name": "告警", "reason": "检测到低风险行为，已记录"}
        else:
            return {"action": "allow", "action_name": "放行", "reason": "安全检测通过"}

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
