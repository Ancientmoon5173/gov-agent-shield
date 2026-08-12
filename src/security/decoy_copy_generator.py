"""
诱饵副本生成器（方案 C 结果级令牌预埋）。

当 Shadow Decoy 路由（方案 A）实际启用时，为会话动态生成
引擎侧诱饵副本，并在副本内容中预埋唯一 Data Provenance Token，
使 Agent 读取到的结果天然携带令牌，无需 after_tool_call 改写。
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import DECOY_COPY_CONFIG
from src.security.data_provenance import (
    DataProvenanceTracker,
    create_data_provenance_tracker,
)


class DecoyCopyGenerator:
    """会话级诱饵副本生成器。"""

    def __init__(
        self,
        tracker: Optional[DataProvenanceTracker] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self._tracker = tracker or create_data_provenance_tracker()
        self._config = dict(config or DECOY_COPY_CONFIG)
        self._root = Path(self._config["root"])

    @property
    def tracker(self) -> DataProvenanceTracker:
        """共享的数据溯源令牌注册表。"""
        return self._tracker

    def create_copy(
        self,
        session_id: str,
        asset_type: str,
        filename: str,
        original_target: str = "",
        inject_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成会话级诱饵副本并预埋令牌。

        Returns:
            {
                "created": bool,
                "copy_path": str,
                "token": str,
                "copy_id": str,
                "inject_mode": str,
                "reason": str,  # created=False 时返回失败原因
            }
        """
        max_injections = int(
            self._config.get("max_injections_per_session", 5)
        )
        if self._tracker.active_count(session_id) >= max_injections:
            return {"created": False, "reason": "max_injections_reached"}

        safe_name = Path(str(filename)).name
        if not safe_name or safe_name in (".", ".."):
            return {"created": False, "reason": "invalid_filename"}

        session_dir = self._sanitize_segment(session_id)
        asset_dir = self._sanitize_segment(asset_type)
        copy_path = self._root / session_dir / asset_dir / safe_name

        try:
            resolved_root = self._root.resolve()
            if not copy_path.resolve().is_relative_to(resolved_root):
                return {"created": False, "reason": "path_escape"}
            copy_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"created": False, "reason": f"io_error:{exc}"}

        token = self._tracker.generate_token()
        mode = inject_mode or str(self._config.get("inject_mode", "text"))
        try:
            copy_path.write_text(
                self._build_content(mode, safe_name, token),
                encoding="utf-8",
            )
        except OSError as exc:
            return {"created": False, "reason": f"io_error:{exc}"}

        copy_id = f"copy-{uuid.uuid4().hex[:8]}"
        self._tracker.register(
            session_id,
            copy_id,
            token,
            metadata={
                "source": "decoy_copy",
                "copy_id": copy_id,
                "copy_path": str(copy_path),
                "asset_type": asset_type,
                "original_target": original_target,
                "inject_mode": mode,
            },
        )
        return {
            "created": True,
            "copy_id": copy_id,
            "copy_path": str(copy_path),
            "token": token,
            "inject_mode": mode,
        }

    def _build_content(self, mode: str, filename: str, token: str) -> str:
        """按注入模式构建副本内容。"""
        if mode == "json_field":
            return json.dumps(
                {
                    "file": filename,
                    "content": "会话级诱饵副本",
                    "provenance_token": token,
                },
                ensure_ascii=False,
                indent=2,
            )
        if mode == "table_row":
            return f"{filename},session_decoy,{token}\n"
        return f"会话级诱饵副本: {filename}\n数据校验标记: {token}\n"

    def _sanitize_segment(self, value: Any) -> str:
        """清理目录段，禁止路径分隔符。"""
        cleaned = str(value).strip().replace("\\", "_").replace("/", "_")
        return cleaned[:64] or "unknown"


def create_decoy_copy_generator(
    tracker: Optional[DataProvenanceTracker] = None,
    config: Optional[Dict[str, Any]] = None,
) -> DecoyCopyGenerator:
    """创建诱饵副本生成器。"""
    return DecoyCopyGenerator(tracker=tracker, config=config)
