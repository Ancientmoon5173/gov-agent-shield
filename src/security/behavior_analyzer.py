"""
行为链风险分析模块（R_behavior）。

分析 Agent 在会话中的工具调用序列，检测异常行为模式。
只依赖 operation 计数和序列规则，不依赖机器学习。

规则：
1. 高频文件访问 - 30秒内 READ >= 3次
2. 敏感读取后外发 - READ 后 60秒内 EXFIL
3. 批量查询 - QUERY 连续 >= 5次
4. 危险工具组合 - QUERY/敏感 READ + EXFIL
5. 行为信号 - 基于资产上下文输出 risk_increment / confidence / evidence
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .operation_map import (
    OPERATION_EXFIL,
    OPERATION_QUERY,
    OPERATION_READ,
    normalize_operation,
)


class BehaviorAnalyzer:
    """行为链风险分析器。"""

    # 窗口时间配置（秒）
    TIME_WINDOWS = {
        "high_frequency": 30,
        "read_then_upload": 60,
        "batch_query": 120,
    }

    SENSITIVE_CONTENT_WORDS = (
        "secret",
        "password",
        "salary",
        "confidential",
        "客户",
        "身份证",
        "工资",
        "薪酬",
        "内部",
        "合同",
        "居民",
        "连接配置",
    )

    def __init__(self):
        # 每个 session 的工具调用历史
        self._history: Dict[str, List[Dict]] = {}

    def record_call(
        self,
        session_id: str,
        tool_name: str,
        params: Dict[str, Any],
        timestamp: Optional[str] = None,
        asset_context: Optional[Dict[str, Any]] = None,
        task_context: Optional[Dict[str, Any]] = None,
    ):
        """记录一次工具调用及其资产上下文。"""
        if session_id not in self._history:
            self._history[session_id] = []
        task_context = dict(task_context or {})
        if not task_context and self._history[session_id]:
            task_context = dict(
                self._history[session_id][-1].get("task_context", {})
            )
        self._history[session_id].append({
            "tool": tool_name,
            "params": params,
            "time": timestamp or datetime.now().isoformat(),
            "operation": normalize_operation(tool_name),
            "asset": dict(asset_context or {}),
            "task_context": task_context,
        })

    def analyze(
        self,
        session_id: str,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        分析指定会话的行为链风险。

        Returns:
            {
                "behavior_score": float,  # R_behavior 评分 0-1
                "risk_type": str,
                "reason": str,
                "details": dict,
                "behavior_signal": dict,
                "operation_history": list,
                "asset_history": list,
                "task_context": dict,
            }
        """
        history = self._history.get(session_id, [])
        if task_context is None and history:
            task_context = history[-1].get("task_context", {})
        if len(history) < 1:
            return {
                "behavior_score": 0.0,
                "risk_type": "none",
                "reason": "行为正常",
                "details": {},
                "behavior_signal": self._empty_behavior_signal(),
                "operation_history": [],
                "asset_history": [],
                "task_context": dict(task_context or {}),
            }

        now = datetime.now()
        frequency_risk = self._check_high_frequency(history, now)
        sequence_risk = self._check_read_then_upload(history, now)
        batch_risk = self._check_batch_query(history, now)
        combo_risk = self._check_dangerous_combo(history, now)
        signal = self._build_behavior_signal(history)
        signal_risk = float(signal.get("risk_increment", 0.0))

        # R_behavior = max(各项风险, ...) 避免重复计分
        scores = [
            signal_risk,
            frequency_risk,
            sequence_risk,
            batch_risk,
            combo_risk,
        ]
        max_score = max(scores)
        max_idx = scores.index(max_score)

        risk_types = [
            "behavior_signal",
            "high_frequency_file_access",
            "sensitive_data_exfiltration",
            "batch_query",
            "dangerous_tool_combo",
        ]
        reasons = [
            f"行为信号: {signal.get('pattern', 'none')}",
            f"高频文件访问: {frequency_risk:.2f}",
            f"敏感读取后外发: {sequence_risk:.2f}",
            f"批量查询: {batch_risk:.2f}",
            f"危险工具组合: {combo_risk:.2f}",
        ]

        return {
            "behavior_score": round(max_score, 3),
            "risk_type": risk_types[max_idx] if max_score > 0 else "none",
            "reason": reasons[max_idx] if max_score > 0 else "行为正常",
            "details": {
                "signal_risk": round(signal_risk, 3),
                "frequency_risk": round(frequency_risk, 3),
                "sequence_risk": round(sequence_risk, 3),
                "batch_risk": round(batch_risk, 3),
                "combo_risk": round(combo_risk, 3),
                "total_calls": len(history),
            },
            "behavior_signal": signal,
            "operation_history": [
                str(c.get("operation", "OTHER")) for c in history
            ],
            "asset_history": [
                c.get("asset", {}) for c in history
            ],
            "task_context": dict(task_context or {}),
        }

    def _get_recent_calls(self, history: List[Dict], seconds: int) -> List[Dict]:
        """获取最近 seconds 秒内的调用记录。"""
        now = datetime.now()
        window_start = now - timedelta(seconds=seconds)
        recent = []
        for call in history:
            try:
                call_time = datetime.fromisoformat(call["time"])
                if call_time >= window_start:
                    recent.append(call)
            except (ValueError, TypeError):
                recent.append(call)
        return recent

    def _check_high_frequency(self, history: List[Dict], now: datetime) -> float:
        """规则1: 高频文件访问。"""
        recent = self._get_recent_calls(
            history, self.TIME_WINDOWS["high_frequency"]
        )
        reads = [c for c in recent if c.get("operation") == OPERATION_READ]
        if len(reads) >= 3:
            return 0.2
        return 0.0

    def _check_read_then_upload(self, history: List[Dict], now: datetime) -> float:
        """规则2: 敏感读取后外发。"""
        recent = self._get_recent_calls(
            history, self.TIME_WINDOWS["read_then_upload"]
        )
        uploads = [c for c in recent if c.get("operation") == OPERATION_EXFIL]
        reads = [c for c in recent if c.get("operation") == OPERATION_READ]

        if not uploads or not reads:
            return 0.0

        for upload in uploads:
            for read in reads:
                if (
                    read["time"] < upload["time"]
                    and self._is_sensitive_read(read)
                ):
                    return 0.4

        return 0.0

    def _check_batch_query(self, history: List[Dict], now: datetime) -> float:
        """规则3: 批量查询。"""
        recent = self._get_recent_calls(
            history, self.TIME_WINDOWS["batch_query"]
        )
        queries = [c for c in recent if c.get("operation") == OPERATION_QUERY]
        if len(queries) >= 5:
            return 0.3
        return 0.0

    def _check_dangerous_combo(self, history: List[Dict], now: datetime) -> float:
        """规则4: 危险工具组合。"""
        recent = self._get_recent_calls(
            history, self.TIME_WINDOWS["read_then_upload"]
        )
        uploads = [c for c in recent if c.get("operation") == OPERATION_EXFIL]
        if not uploads:
            return 0.0

        for upload in uploads:
            for call in recent:
                if call["time"] >= upload["time"]:
                    continue
                if call.get("operation") == OPERATION_QUERY:
                    return 0.5
                if (
                    call.get("operation") == OPERATION_READ
                    and self._is_sensitive_read(call)
                ):
                    return 0.5

        return 0.0

    def _build_behavior_signal(self, history: List[Dict]) -> Dict[str, Any]:
        """基于 operation + asset_context 生成会话行为信号。"""
        for index, call in enumerate(history):
            if call.get("operation") != OPERATION_EXFIL:
                continue
            prior = history[:index]
            if any(
                c.get("operation") == OPERATION_READ
                and self._is_sensitive_read(c)
                for c in prior
            ):
                return {
                    "pattern": "HIGH_RISK_DATA_EXFIL_CHAIN",
                    "risk_increment": 0.3,
                    "confidence": 0.9,
                    "evidence": [
                        "read_high_sensitive_asset",
                        "exfil_after_sensitive_read",
                    ],
                }
            if any(c.get("operation") == OPERATION_QUERY for c in prior):
                return {
                    "pattern": "QUERY_DATA_EXFIL_CHAIN",
                    "risk_increment": 0.3,
                    "confidence": 0.8,
                    "evidence": [
                        "query_sensitive_data",
                        "exfil_after_query",
                    ],
                }

        for call in history:
            asset = call.get("asset") or {}
            sensitivity = str(asset.get("sensitivity", "LOW")).upper()
            if call.get("operation") != OPERATION_READ:
                continue
            if sensitivity == "CRITICAL":
                return {
                    "pattern": "CRITICAL_ASSET_ACCESS",
                    "risk_increment": 0.15,
                    "confidence": 0.9,
                    "evidence": ["read_critical_asset"],
                }
            if sensitivity == "HIGH":
                return {
                    "pattern": "HIGH_ASSET_ACCESS",
                    "risk_increment": 0.1,
                    "confidence": 0.8,
                    "evidence": ["read_high_sensitive_asset"],
                }

        return self._empty_behavior_signal()

    def _is_sensitive_read(self, call: Dict[str, Any]) -> bool:
        """判断一次 READ 是否涉及高敏资产或敏感内容。"""
        asset = call.get("asset") or {}
        sensitivity = str(asset.get("sensitivity", "LOW")).upper()
        if sensitivity in ("SENSITIVE", "HIGH", "CRITICAL"):
            return True
        text = str(call.get("params", {})).lower()
        return any(word in text for word in self.SENSITIVE_CONTENT_WORDS)

    def _empty_behavior_signal(self) -> Dict[str, Any]:
        return {
            "pattern": "none",
            "risk_increment": 0.0,
            "confidence": 0.0,
            "evidence": [],
        }

    def reset_session(self, session_id: str):
        """重置会话历史（测试或新会话时使用）。"""
        if session_id in self._history:
            del self._history[session_id]

    # 预留扩展接口
    def future_anomaly_detector(self, session_id: str) -> float:
        """
        未来异常检测扩展接口。
        当前返回 0，后续可替换为统计异常检测。
        """
        return 0.0


def create_behavior_analyzer() -> BehaviorAnalyzer:
    """创建行为分析器实例。"""
    return BehaviorAnalyzer()
