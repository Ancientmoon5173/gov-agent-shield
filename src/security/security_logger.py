"""
安全事件日志记录器。

记录每次安全检查的完整链路：输入 → 检测 → 评分 → 处置。
用于赛后审计和演示回放。
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import AUDIT_DIR


class SecurityLogger:
    """安全事件日志记录器。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (AUDIT_DIR / "security_events.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    check_type TEXT NOT NULL,
                    input_text TEXT,
                    tool_name TEXT,
                    tool_params TEXT,
                    risk_score REAL,
                    risk_level TEXT,
                    disposition TEXT,
                    details TEXT,
                    event_type TEXT,
                    policy_id TEXT,
                    decision_reason TEXT,
                    defense_stage TEXT,
                    chain_summary TEXT
                )
            """)
            # 兼容旧库：逐列补齐缺失字段
            for column in (
                "event_type",
                "policy_id",
                "decision_reason",
                "defense_stage",
                "chain_summary",
            ):
                try:
                    conn.execute(
                        f"ALTER TABLE security_events ADD COLUMN {column} TEXT"
                    )
                except sqlite3.OperationalError:
                    # 列已存在时忽略
                    pass
            conn.commit()

    def log_check(self, session_id: str, check_type: str, input_text: str = "",
                  tool_name: str = "", tool_params: dict = None,
                  risk_score: float = 0.0, risk_level: str = "LOW",
                  disposition: str = "allow", details: dict = None,
                  event_type: str = "", policy_id: str = "",
                  decision_reason: str = "", defense_stage: str = "",
                  chain_summary: str = ""):
        """记录一次安全检查事件。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO security_events
                   (timestamp, session_id, check_type, input_text, tool_name,
                    tool_params, risk_score, risk_level, disposition, details,
                    event_type, policy_id, decision_reason, defense_stage,
                    chain_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    session_id, check_type,
                    input_text[:300] if input_text else "",
                    tool_name,
                    json.dumps(tool_params or {}, ensure_ascii=False),
                    round(risk_score, 3),
                    risk_level, disposition,
                    json.dumps(details or {}, ensure_ascii=False),
                    event_type, policy_id, decision_reason, defense_stage,
                    chain_summary,
                ),
            )
            conn.commit()

    def get_recent_events(self, limit: int = 50) -> list:
        """获取最近的安全事件。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM security_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_session_events(self, session_id: str) -> list:
        """获取指定会话的所有安全事件。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM security_events WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_summary(self) -> dict:
        """获取安全事件摘要统计。"""
        events = self.get_recent_events(500)
        counts = {"allow": 0, "review": 0, "block": 0, "kill": 0}
        level_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "VERY_HIGH": 0, "CRITICAL": 0}
        for e in events:
            d = e.get("disposition", "allow")
            if d in counts:
                counts[d] += 1
            lv = e.get("risk_level", "LOW")
            if lv in level_counts:
                level_counts[lv] += 1
        return {
            "total_events": len(events),
            "disposition_counts": counts,
            "level_distribution": level_counts,
        }


def create_security_logger() -> SecurityLogger:
    """创建安全日志记录器。"""
    return SecurityLogger()
