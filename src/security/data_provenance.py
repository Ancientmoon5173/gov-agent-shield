"""
数据溯源令牌（Data Provenance Token，方案 C 第一阶段）。

只实现外发/写入类工具参数扫描：
- 本模块维护令牌注册表（内存实现）
- 引擎生成唯一令牌，可预埋进诱饵副本内容，或由插件在
  tool_result_persist 阶段注入工具结果消息
- before_tool_call 扫描即将执行的外发/写入类工具参数，
  命中活跃令牌即生成泄漏信号，由 Orchestrator 阻断并审计
"""

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from src.config import DATA_PROVENANCE_CONFIG


class DataProvenanceTracker:
    """数据溯源令牌注册表与泄漏扫描器。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = dict(config or DATA_PROVENANCE_CONFIG)
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        session_id: str,
        tool_call_id: str,
        token_value: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """注册一个已注入的令牌。"""
        expire_hours = float(self._config.get("expire_hours", 24))
        now = time.time()
        with self._lock:
            self._tokens[token_value] = {
                "session_id": session_id,
                "tool_call_id": tool_call_id,
                "metadata": metadata or {},
                "created_at": now,
                "expires_at": now + expire_hours * 3600,
            }
        return token_value

    def generate_token(self, prefix: Optional[str] = None) -> str:
        """生成唯一数据溯源令牌。"""
        token_prefix = prefix or str(self._config.get("token_prefix", "DPT"))
        return f"{token_prefix}-{uuid.uuid4().hex[:12]}"

    def active_count(self, session_id: str) -> int:
        """统计会话当前活跃令牌数（用于注入上限控制）。"""
        now = time.time()
        with self._lock:
            return sum(
                1
                for info in self._tokens.values()
                if info.get("session_id") == session_id
                and info.get("expires_at", 0) > now
            )

    def revoke(self, token_value: str) -> None:
        """撤销一个令牌，使其不再参与泄漏扫描。"""
        with self._lock:
            self._tokens.pop(token_value, None)

    def should_inject(self, tool_name: str) -> bool:
        """是否需要对当前工具结果注入令牌。"""
        return (
            bool(self._config.get("inject_on_sensitive_read", False))
            and tool_name in self._config.get("inject_tools", [])
        )

    def inject_mode(self) -> str:
        """返回结果注入模式。"""
        return str(self._config.get("inject_mode", "text"))

    def scan_leak(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        扫描外发/写入类工具参数是否携带活跃令牌。

        Returns:
            {
                "hit": bool,
                "token": str,
                "token_info": dict,
            }
        """
        if not self._config.get("enabled", True):
            return self._empty()

        target_tools = self._config.get("target_tools", [])
        if target_tools and tool_name not in target_tools:
            return self._empty()

        text = self._collect_text(params)
        if not text:
            return self._empty()

        now = time.time()
        with self._lock:
            for token, info in self._tokens.items():
                if info.get("expires_at", 0) <= now:
                    continue
                if token and token in text:
                    return {
                        "hit": True,
                        "token": token,
                        "token_info": info,
                    }
        return self._empty()

    def _collect_text(self, params: Dict[str, Any]) -> str:
        """递归收集参数中的字符串文本。"""
        parts: List[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                for v in value.values():
                    walk(v)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    walk(v)

        walk(params or {})
        return " ".join(parts)

    def _empty(self) -> Dict[str, Any]:
        return {"hit": False, "token": "", "token_info": {}}


def create_data_provenance_tracker() -> DataProvenanceTracker:
    """创建数据溯源令牌追踪器。"""
    return DataProvenanceTracker()
