"""
审计日志记录器。
结构化记录所有安全事件。
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from src.config import AUDIT_DIR

class AuditLogger:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (AUDIT_DIR / 'audit.db')
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, event_type TEXT NOT NULL, session_id TEXT, user_input TEXT, agent_action TEXT, tool_calls TEXT, risk_score REAL, risk_level TEXT, disposition TEXT, details TEXT)')
            conn.commit()

    def log_event(self, event_type, session_id='', user_input='', agent_action='', tool_calls=None, risk_score=0.0, risk_level='LOW', disposition='allow', details=None):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('INSERT INTO audit_events (timestamp, event_type, session_id, user_input, agent_action, tool_calls, risk_score, risk_level, disposition, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (datetime.now(timezone.utc).isoformat(), event_type, session_id, user_input[:500], agent_action[:500], json.dumps(tool_calls or [], ensure_ascii=False), risk_score, risk_level, disposition, json.dumps(details or {}, ensure_ascii=False)))
            conn.commit()

    def get_recent_events(self, limit=50):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_events_by_session(self, session_id):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM audit_events WHERE session_id = ? ORDER BY id ASC', (session_id,)).fetchall()
            return [dict(r) for r in rows]
