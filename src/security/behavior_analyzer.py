"""
行为链风险分析模块（R_behavior）。

分析 Agent 在会话中的工具调用序列，检测异常行为模式。
只依赖计数和序列规则，不依赖机器学习。

规则：
1. 高频文件访问 - 30秒内 read_document >= 3次
2. 敏感读取后外发 - read_document 后 60秒内 upload_data
3. 批量查询 - query_citizen_info 连续 >= 5次
4. 危险工具组合 - query_citizen_info/read_document + upload_data
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


class BehaviorAnalyzer:
    """行为链风险分析器。"""

    # 窗口时间配置（秒）
    TIME_WINDOWS = {
        "high_frequency": 30,
        "read_then_upload": 60,
        "batch_query": 120,
    }

    def __init__(self):
        # 每个 session 的工具调用历史
        self._history: Dict[str, List[Dict]] = {}

    def record_call(self, session_id: str, tool_name: str,
                    params: Dict[str, Any], timestamp: Optional[str] = None):
        """记录一次工具调用。"""
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append({
            "tool": tool_name,
            "params": params,
            "time": timestamp or datetime.now().isoformat(),
        })

    def analyze(self, session_id: str) -> Dict[str, Any]:
        """
        分析指定会话的行为链风险。

        Returns:
            {
                "behavior_score": float,  # R_behavior 评分 0-1
                "risk_type": str,         # 风险类型
                "reason": str,            # 触发原因
                "details": dict,          # 详细检测信息
            }
        """
        history = self._history.get(session_id, [])
        if len(history) < 1:
            return {
                "behavior_score": 0.0,
                "risk_type": "none",
                "reason": "行为正常",
                "details": {},
            }

        now = datetime.now()
        frequency_risk = self._check_high_frequency(history, now)
        sequence_risk = self._check_read_then_upload(history, now)
        batch_risk = self._check_batch_query(history, now)
        combo_risk = self._check_dangerous_combo(history, now)

        # R_behavior = max(各项风险, ...) 避免重复计分
        scores = [frequency_risk, sequence_risk, batch_risk, combo_risk]
        max_score = max(scores)
        max_idx = scores.index(max_score)

        risk_types = [
            "high_frequency_file_access",
            "sensitive_data_exfiltration",
            "batch_query",
            "dangerous_tool_combo",
        ]
        reasons = [
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
                "frequency_risk": round(frequency_risk, 3),
                "sequence_risk": round(sequence_risk, 3),
                "batch_risk": round(batch_risk, 3),
                "combo_risk": round(combo_risk, 3),
                "total_calls": len(history),
            },
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
        recent = self._get_recent_calls(history, self.TIME_WINDOWS["high_frequency"])
        doc_reads = [c for c in recent if c["tool"] == "read_document"]
        if len(doc_reads) >= 3:
            return 0.2
        return 0.0

    def _check_read_then_upload(self, history: List[Dict], now: datetime) -> float:
        """规则2: 敏感读取后外发。"""
        recent = self._get_recent_calls(history, self.TIME_WINDOWS["read_then_upload"])
        uploads = [c for c in recent if c["tool"] == "upload_data"]
        reads = [c for c in recent if c["tool"] == "read_document"]

        if not uploads or not reads:
            return 0.0

        # 检查是否有 read 在 upload 之前
        for upload in uploads:
            for read in reads:
                if read["time"] < upload["time"]:
                    # 检查读取内容是否含敏感词
                    content = str(read.get("params", {}))
                    sensitive_words = ["secret", "password", "合同", "身份证", "内部"]
                    extra = 0.0
                    for word in sensitive_words:
                        if word in content:
                            extra = 0.2
                            break
                    return min(0.4 + extra, 1.0)

        return 0.0

    def _check_batch_query(self, history: List[Dict], now: datetime) -> float:
        """规则3: 批量查询。"""
        recent = self._get_recent_calls(history, self.TIME_WINDOWS["batch_query"])
        queries = [c for c in recent if c["tool"] == "query_citizen_info"]
        if len(queries) >= 5:
            return 0.3
        return 0.0

    def _check_dangerous_combo(self, history: List[Dict], now: datetime) -> float:
        """规则4: 危险工具组合。"""
        recent = self._get_recent_calls(history, self.TIME_WINDOWS["read_then_upload"])
        uploads = [c for c in recent if c["tool"] == "upload_data"]
        if not uploads:
            return 0.0

        # 检查 upload 之前是否有敏感操作
        for upload in uploads:
            for call in recent:
                if call["time"] < upload["time"]:
                    if call["tool"] in ("query_citizen_info", "read_document"):
                        return 0.5

        return 0.0

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
