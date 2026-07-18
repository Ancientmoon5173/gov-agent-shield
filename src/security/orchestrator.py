"""
安全协调器（SecurityOrchestrator）。

这是安全层对外的唯一接口。Agent 只通过以下三个方法完成安全检查：
- check_input()     → 输入注入检测
- check_tool_call() → 工具调用检测（参数 + 行为链）
- check_output()    → 输出敏感数据检测

内部协调 6 个模块：InputDetector, ToolGateway, ParameterChecker,
BehaviorAnalyzer, OutputGuard, RiskScorer, DispositionEngine, SecurityLogger
"""

from typing import Dict, Any, Optional

from src.input_guard import InputDetector
from src.input_guard.rules import get_default_detector
from src.tool_gateway import ToolGateway
from src.tool_gateway.policies import get_default_gateway
from src.risk_engine import RiskScorer, DispositionEngine
from src.config import (
    RISK_THRESHOLD_LOW, RISK_THRESHOLD_MEDIUM, RISK_THRESHOLD_HIGH,
)

from .tool_risk_config import TOOL_RISK_CONFIG
from .parameter_checker import ParameterChecker, create_parameter_checker
from .behavior_analyzer import BehaviorAnalyzer, create_behavior_analyzer
from .output_guard import OutputGuard, create_output_guard
from .security_logger import SecurityLogger, create_security_logger
from .permission_checker import PermissionChecker, create_permission_checker


# 风险融合权重
RISK_WEIGHTS = {
    "R_input": 0.20,
    "R_tool": 0.35,
    "R_output": 0.25,
    "R_behavior": 0.20,
}


def _calculate_final_risk(
    r_input: float,
    r_tool: float,
    r_output: float,
    r_behavior: float,
) -> Dict[str, Any]:
    """
    四维风险融合算法。

    BaseRisk = weighted average
    FinalRisk = max(BaseRisk, MaxRisk * 0.85)
    """
    scores = {
        "R_input": round(r_input, 3),
        "R_tool": round(r_tool, 3),
        "R_output": round(r_output, 3),
        "R_behavior": round(r_behavior, 3),
    }

    weighted_sum = (
        r_input * RISK_WEIGHTS["R_input"]
        + r_tool * RISK_WEIGHTS["R_tool"]
        + r_output * RISK_WEIGHTS["R_output"]
        + r_behavior * RISK_WEIGHTS["R_behavior"]
    )
    total_weight = sum(RISK_WEIGHTS.values())
    base_risk = weighted_sum / total_weight if total_weight > 0 else 0
    max_risk = max(r_input, r_tool, r_output, r_behavior)

    final_risk = max(base_risk, max_risk * 0.85)

    # 5 级风险等级
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
    安全协调器。

    使用方式:
        orchestrator = create_orchestrator()
        result = orchestrator.check_tool_call("session-1", "read_document", {"file_path": "secret.pdf"})
        if result["blocked"]:
            print(f"阻断: {result['reason']}")
    """

    def __init__(
        self,
        input_detector: InputDetector = None,
        tool_gateway: ToolGateway = None,
        parameter_checker: ParameterChecker = None,
        behavior_analyzer: BehaviorAnalyzer = None,
        output_guard: OutputGuard = None,
        permission_checker: PermissionChecker = None,
        security_logger: SecurityLogger = None,
    ):
        # 初始化各检测模块
        self.input_detector = input_detector or get_default_detector()
        self.tool_gateway = tool_gateway or get_default_gateway()
        self.parameter_checker = parameter_checker or create_parameter_checker()
        self.behavior_analyzer = behavior_analyzer or create_behavior_analyzer()
        self.output_guard = output_guard or create_output_guard()
        self.permission_checker = permission_checker or create_permission_checker()
        self.security_logger = security_logger or create_security_logger()

        # 处置引擎（复用 risk_engine 模块）
        self.disposition_engine = DispositionEngine()

    def check_input(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """
        检查用户输入的安全性。

        Args:
            session_id: 会话ID
            user_input: 用户输入的文本

        Returns:
            {
                "passed": bool,          # 是否通过检查
                "risk_score": float,     # R_input 评分
                "risk_level": str,       # 风险等级
                "action": str,           # 处置动作
                "action_name": str,      # 动作中文名
                "reason": str,           # 原因说明
                "findings": list,        # 检测发现
            }
        """
        scan_result = self.input_detector.scan(user_input)
        r_input = scan_result.get("risk_score", 0.0)

        risk = _calculate_final_risk(
            r_input=r_input, r_tool=0.0, r_output=0.0, r_behavior=0.0,
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
        检查工具调用的安全性（核心检测点）。

        检测流程：
        1. 工具基础风险分（ToolBase）
        2. 参数风险检测（ParameterRisk）
        3. 行为链风险分析（R_behavior）
        4. 综合评分
        5. 处置决策

        Returns:
            {
                "blocked": bool,         # 是否被阻断
                "risk_score": float,     # 最终风险评分
                "risk_level": str,       # 风险等级
                "action": str,           # 处置动作
                "action_name": str,      # 动作中文名
                "reason": str,           # 阻断/放行原因
                "dimensions": dict,      # 各维度评分明细
            }
        """
        tool_config = TOOL_RISK_CONFIG.get(tool_name, {})
        r_tool_base = tool_config.get("base_risk", 0.5)

        # 1. 参数风险
        param_result = self.parameter_checker.check(tool_name, params)
        r_tool = min(r_tool_base + param_result["risk_score"], 1.0)

        # 2. 行为链风险
        self.behavior_analyzer.record_call(session_id, tool_name, params)
        behavior_result = self.behavior_analyzer.analyze(session_id)

        # 3. 权限风险（MVP返回0）
        r_permission = self.permission_checker.calculate_permission_risk()

        # 4. 综合评分（R_input 来自输入检测，这里复用或默认为0）
        r_input = 0.0  # check_input 已经在前置调用中完成

        risk = _calculate_final_risk(
            r_input=r_input,
            r_tool=r_tool,
            r_output=0.0,  # 输出检查在工具执行后
            r_behavior=behavior_result["behavior_score"],
        )

        # 5. 处置决策（使用5级阈值）
        disposition = self._map_disposition(risk["total_score"], risk["level"])
        blocked = disposition["action"] in ("block", "kill")

        # 6. 记录日志
        self.security_logger.log_check(
            session_id=session_id, check_type="tool_call",
            input_text="", tool_name=tool_name,
            tool_params=params,
            risk_score=risk["total_score"],
            risk_level=risk["level"],
            disposition=disposition["action"],
            details={
                "dimensions": risk["dimensions"],
                "param_findings": param_result.get("findings", []),
                "behavior": behavior_result,
                "tool_config": tool_config,
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
        }

    def check_output(self, session_id: str, tool_name: str,
                     output_text: str) -> Dict[str, Any]:
        """
        检查工具输出是否包含敏感数据。

        Returns:
            {
                "has_sensitive_data": bool,
                "risk_score": float,
                "action": str,
                "masked_output": str,  # 脱敏后的文本
            }
        """
        scan_result = self.output_guard.scan(output_text)

        if scan_result["has_sensitive_data"]:
            masked = self.output_guard.mask_sensitive(output_text)

            risk = _calculate_final_risk(
                r_input=0.0, r_tool=0.0,
                r_output=scan_result["risk_score"],
                r_behavior=0.0,
            )

            disposition = self._map_disposition(
                risk["total_score"], risk["level"])

            self.security_logger.log_check(
                session_id=session_id, check_type="output",
                tool_name=tool_name,
                risk_score=risk["total_score"],
                risk_level=risk["level"],
                disposition="masked",
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
        """
        5级风险映射处置动作。

        LOW(0-0.3):      放行
        MEDIUM(0.3-0.5): 放行+标记
        HIGH(0.5-0.7):   需要人工审批
        VERY_HIGH(0.7-0.85): 阻断当前操作
        CRITICAL(0.85+): 任务熔断
        """
        if level == "CRITICAL":
            return {"action": "kill", "action_name": "熔断",
                    "reason": "检测到严重安全攻击，已终止整个任务"}
        elif level == "VERY_HIGH":
            return {"action": "block", "action_name": "阻断",
                    "reason": "检测到高风险操作，已阻断"}
        elif level == "HIGH":
            return {"action": "review", "action_name": "审批",
                    "reason": "检测到可疑行为，需要人工确认"}
        elif level == "MEDIUM":
            return {"action": "warn", "action_name": "告警",
                    "reason": "检测到低风险行为，已记录"}
        else:
            return {"action": "allow", "action_name": "放行",
                    "reason": "安全检测通过"}

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
