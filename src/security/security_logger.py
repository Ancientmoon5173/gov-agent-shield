"""
安全事件日志记录器（V1：工具调用级闭环 + 审计链路）。

记录每次安全检查的完整链路：
输入 → 检测 → 评分 → 处置 → 审批 → 执行结果，
并为每一次工具调用分配唯一身份（chain_id / call_id / event_uuid / step_no），
满足“Security Decision → Enforcement → Audit”闭环要求。
"""

import contextvars
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import AUDIT_DIR

# ========================
# Schema v2（旧库通过 ALTER TABLE 兼容升级）
# ========================
_EXTRA_COLUMNS = (
    # 旧库缺失的基础审计列（V0/V1 早期 schema）
    ("event_type", "TEXT"),
    ("policy_id", "TEXT"),
    ("decision_reason", "TEXT"),
    ("defense_stage", "TEXT"),
    ("chain_summary", "TEXT"),
    # Schema v2 链路身份与闭环状态列
    ("event_uuid", "TEXT"),
    ("chain_id", "TEXT"),
    ("call_id", "TEXT"),
    ("plugin_tool_call_id", "TEXT"),
    ("step_no", "INTEGER"),
    ("approval_id", "TEXT"),
    ("execution_status", "TEXT"),
    ("reviewer", "TEXT"),
    ("decided_at", "TEXT"),
    ("executed_at", "TEXT"),
    ("tool_error", "TEXT"),
    # Schema v3（Phase1）：事件因果边
    ("parent_event_id", "TEXT"),
    ("trigger_event_id", "TEXT"),
)

_SECURITY_EVENTS_DDL = """
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
"""

_AUDIT_APPROVALS_DDL = """
CREATE TABLE IF NOT EXISTS audit_approvals (
    approval_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    chain_id TEXT,
    session_id TEXT NOT NULL,
    agent_id TEXT,
    tool_name TEXT,
    tool_params TEXT,
    decision TEXT DEFAULT 'review',
    policy_id TEXT,
    decision_reason TEXT,
    risk_score REAL,
    risk_level TEXT,
    status TEXT DEFAULT 'pending',
    requested_at TEXT,
    decided_at TEXT,
    reviewer TEXT,
    decision_comment TEXT,
    execution_status TEXT DEFAULT 'PENDING_APPROVAL'
)
"""

_AUDIT_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS audit_sessions (
    session_id TEXT PRIMARY KEY,
    task_id TEXT,
    user_id TEXT,
    started_at TEXT,
    ended_at TEXT,
    status TEXT DEFAULT 'open'
)
"""

_AUDIT_CHAINS_DDL = """
CREATE TABLE IF NOT EXISTS audit_chains (
    chain_id TEXT PRIMARY KEY,
    session_id TEXT,
    chain_type TEXT DEFAULT 'session',
    started_at TEXT,
    ended_at TEXT,
    final_risk REAL,
    final_disposition TEXT,
    status TEXT DEFAULT 'open'
)
"""

_AUDIT_CALLS_DDL = """
CREATE TABLE IF NOT EXISTS audit_calls (
    call_id TEXT PRIMARY KEY,
    session_id TEXT,
    chain_id TEXT,
    seq_no INTEGER,
    tool_name TEXT,
    started_at TEXT,
    ended_at TEXT,
    decision TEXT,
    execution_status TEXT,
    parent_call_id TEXT
)
"""

_RISK_ESCALATIONS_DDL = """
CREATE TABLE IF NOT EXISTS risk_escalations (
    escalation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id TEXT,
    call_id TEXT,
    from_event_uuid TEXT,
    to_event_uuid TEXT,
    from_score REAL,
    to_score REAL,
    delta REAL,
    dominant_dimension TEXT,
    trigger_reason TEXT,
    decision TEXT,
    timestamp TEXT
)
"""

# audit_approvals 追加列（关联决策事件）
_APPROVALS_EXTRA_COLUMNS = (
    ("event_uuid", "TEXT"),
)

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_se_chain ON security_events(chain_id)",
    "CREATE INDEX IF NOT EXISTS idx_se_call ON security_events(call_id)",
    "CREATE INDEX IF NOT EXISTS idx_se_session ON security_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_se_type ON security_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_ap_status ON audit_approvals(status)",
    "CREATE INDEX IF NOT EXISTS idx_ap_call ON audit_approvals(call_id)",
    "CREATE INDEX IF NOT EXISTS idx_ap_session ON audit_approvals(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_se_parent ON security_events(parent_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_se_trigger ON security_events(trigger_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_ch_session ON audit_chains(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_calls_chain ON audit_calls(chain_id)",
    "CREATE INDEX IF NOT EXISTS idx_calls_session ON audit_calls(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_esc_chain ON risk_escalations(chain_id)",
)

# ========================
# 常量
# ========================
EVENT_APPROVAL_OUTCOME = "approval_outcome"
EVENT_EXECUTION_OUTCOME = "execution_outcome"

# 当前工具调用上下文（线程隔离；open_call/clear_call 维护）
_ACTIVE_CALL = contextvars.ContextVar(
    "security_active_call", default=None
)

# 事件行 step_no 自动推导：优先按 event_type，其次按 defense_stage
_STEP_BY_EVENT = {
    "asset_resolved": 10,
    "data_classified": 15,
    "decoy_virtual_hit": 20,
    "data_provenance_injected": 35,
    "data_provenance_leak_detected": 90,
    "decoy_route_triggered": 50,
    "decoy.deployment_missing": 50,
}
_STEP_BY_STAGE = {
    "input_guard": 5,
    "asset_resolver": 10,
    "data_classifier": 15,
    "behavior_observer": 20,
    "behavior_analyzer": 20,
    "decoy_manager": 30,
    "data_provenance": 35,
    "permission_checker": 40,
    "risk_engine": 80,
    "decoy_copy_generator": 50,
}


def _resolve_step_no(event_type: str, defense_stage: str):
    if event_type and event_type in _STEP_BY_EVENT:
        return _STEP_BY_EVENT[event_type]
    if defense_stage and defense_stage in _STEP_BY_STAGE:
        return _STEP_BY_STAGE[defense_stage]
    return None

STATUS_PENDING_EXECUTION = "PENDING_EXECUTION"
STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
STATUS_EXECUTED = "EXECUTED"
STATUS_EXECUTION_ERROR = "EXECUTION_ERROR"
STATUS_NOT_EXECUTED = "NOT_EXECUTED"

# disposition 升级序（用于判断风险升级）
_DISPOSITION_RANK = {
    "allow": 0,
    "warn": 1,
    "review": 2,
    "block": 3,
    "kill": 4,
}

# 事件 -> 会话级风险锚点类型
_ANCHOR_BY_EVENT = {
    "prompt_injection": "input",
    "data_exfiltration": "input",
    "data_poisoning": "input",
    "input_risk": "input",
    "asset_resolved": "asset",
    "data_classified": "data",
    "decoy_virtual_hit": "decoy_hint",
    "decoy_route_triggered": "decoy_route",
    "data_provenance_injected": "dpt_inject",
    "data_provenance_leak_detected": "dpt_leak",
    "permission_violation": "permission",
    "behavior_chain": "behavior",
}


class SecurityLogger:
    """安全事件日志记录器。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (AUDIT_DIR / "security_events.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._approval_seq = 0
        # 会话级“最近风险锚点 / 最近决策”，用于显式因果（不依赖物理行序）
        self._session_anchor: Dict[str, Dict[str, Any]] = {}
        self._session_decision: Dict[str, Dict[str, Any]] = {}
        self._init_db()

    # ---------------- 工具函数 ----------------

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_event_uuid() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _new_call_id() -> str:
        return f"CALL-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def chain_id_for_session(session_id: str) -> Optional[str]:
        """按会话生成稳定的 chain_id（确定性，跨进程一致）。"""
        if not session_id:
            return None
        digest = hashlib.md5(str(session_id).encode("utf-8")).hexdigest()[:12]
        return f"C-{digest}"

    # ---------------- 初始化 ----------------

    def _init_db(self):
        """初始化数据库表、兼容升级与索引。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(_SECURITY_EVENTS_DDL)
            conn.execute(_AUDIT_APPROVALS_DDL)
            conn.execute(_AUDIT_SESSIONS_DDL)
            conn.execute(_AUDIT_CHAINS_DDL)
            conn.execute(_AUDIT_CALLS_DDL)
            conn.execute(_RISK_ESCALATIONS_DDL)
            for column, ctype in _EXTRA_COLUMNS:
                try:
                    conn.execute(
                        f"ALTER TABLE security_events ADD COLUMN {column} {ctype}"
                    )
                except sqlite3.OperationalError:
                    # 列已存在时忽略
                    pass
            for column, ctype in _APPROVALS_EXTRA_COLUMNS:
                try:
                    conn.execute(
                        f"ALTER TABLE audit_approvals ADD COLUMN {column} {ctype}"
                    )
                except sqlite3.OperationalError:
                    # 列已存在时忽略
                    pass
            for sql in _INDEX_SQL:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM audit_approvals"
                )
                self._approval_seq = int(cur.fetchone()[0])
            except sqlite3.OperationalError:
                self._approval_seq = 0
            conn.commit()

    # ---------------- 写入 ----------------

    def log_check(
        self,
        session_id: str,
        check_type: str,
        input_text: str = "",
        tool_name: str = "",
        tool_params: dict = None,
        risk_score: float = 0.0,
        risk_level: str = "LOW",
        disposition: str = "allow",
        details: dict = None,
        event_type: str = "",
        policy_id: str = "",
        decision_reason: str = "",
        defense_stage: str = "",
        chain_summary: str = "",
        *,
        event_uuid: str = None,
        chain_id: str = None,
        call_id: str = None,
        plugin_tool_call_id: str = None,
        step_no: int = None,
        approval_id: str = None,
        execution_status: str = None,
        reviewer: str = None,
        decided_at: str = None,
        executed_at: str = None,
        tool_error: str = None,
        parent_event_id: str = None,
        trigger_event_id: str = None,
    ):
        """记录一次安全检查事件（含链路身份与执行状态字段）。"""
        now = self._now()
        active = _ACTIVE_CALL.get()
        if call_id is None and active:
            call_id = active.get("call_id")
        if plugin_tool_call_id is None and active:
            plugin_tool_call_id = active.get("plugin_tool_call_id")
        if chain_id is None:
            chain_id = (
                (active.get("chain_id") if active else None)
                or self.chain_id_for_session(session_id)
            )
        if step_no is None:
            step_no = _resolve_step_no(event_type, defense_stage)
        resolved_event_uuid = event_uuid or self._new_event_uuid()
        # 因果边：parent = 本调用内上一条事件；trigger = 业务规则显式确定的上游触发事件
        if parent_event_id is None and active and active.get("call_id") == call_id:
            parent_event_id = active.get("last_event_uuid")
        if trigger_event_id is None:
            trigger_event_id = self._resolve_trigger_event(
                session_id=session_id,
                event_type=event_type,
                check_type=check_type,
                defense_stage=defense_stage,
                disposition=disposition,
                step_no=step_no,
                details=details or {},
                risk_score=float(risk_score or 0.0),
            )
        columns = (
            "timestamp", "session_id", "check_type", "input_text", "tool_name",
            "tool_params", "risk_score", "risk_level", "disposition", "details",
            "event_type", "policy_id", "decision_reason", "defense_stage",
            "chain_summary", "event_uuid", "chain_id", "call_id",
            "plugin_tool_call_id", "step_no", "approval_id", "execution_status",
            "reviewer", "decided_at", "executed_at", "tool_error",
            "parent_event_id", "trigger_event_id",
        )
        values = (
            now,
            session_id,
            check_type,
            str(input_text)[:300] if input_text else "",
            tool_name,
            json.dumps(tool_params or {}, ensure_ascii=False),
            round(float(risk_score or 0.0), 3),
            risk_level,
            disposition,
            json.dumps(details or {}, ensure_ascii=False),
            event_type,
            policy_id,
            decision_reason,
            defense_stage,
            chain_summary,
            resolved_event_uuid,
            chain_id,
            call_id,
            plugin_tool_call_id,
            step_no,
            approval_id,
            execution_status,
            reviewer,
            decided_at,
            executed_at,
            tool_error,
            parent_event_id,
            trigger_event_id,
        )
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO security_events ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(sql, values)
            conn.commit()

        self._housekeep_after_event(
            session_id=session_id,
            call_id=call_id,
            chain_id=chain_id,
            event_uuid=resolved_event_uuid,
            event_type=event_type,
            step_no=step_no,
            disposition=disposition,
            risk_score=float(risk_score or 0.0),
            risk_level=risk_level,
            execution_status=execution_status,
            decision_reason=decision_reason,
            details=details or {},
            timestamp=now,
        )

    def create_approval(
        self,
        session_id: str,
        call_id: str,
        agent_id: str = "",
        tool_name: str = "",
        tool_params: dict = None,
        policy_id: str = "",
        decision_reason: str = "",
        risk_score: float = 0.0,
        risk_level: str = "LOW",
        decision: str = "review",
    ) -> str:
        """创建审批记录（SQLite，跨进程可见）。返回 approval_id。"""
        now = self._now()
        with sqlite3.connect(str(self.db_path)) as conn:
            self._approval_seq += 1
            approval_id = (
                f"AP-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                f"-{self._approval_seq:04d}"
            )
            conn.execute(
                """INSERT INTO audit_approvals
                   (approval_id, call_id, chain_id, session_id, agent_id,
                    tool_name, tool_params, decision, policy_id,
                    decision_reason, risk_score, risk_level, status,
                    requested_at, execution_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    approval_id,
                    call_id,
                    self.chain_id_for_session(session_id),
                    session_id,
                    agent_id,
                    tool_name,
                    json.dumps(tool_params or {}, ensure_ascii=False),
                    decision,
                    policy_id,
                    decision_reason,
                    round(float(risk_score or 0.0), 3),
                    risk_level,
                    "pending",
                    now,
                    STATUS_PENDING_APPROVAL,
                ),
            )
            conn.commit()
        return approval_id

    def resolve_approval(
        self,
        approval_id: str,
        action: str,
        reviewer: str = "",
        comment: str = "",
    ) -> Dict[str, Any]:
        """
        审批通过/拒绝。

        action ∈ approve | deny：
        - approve → status=approved，决策行 execution_status=EXECUTED
        - deny    → status=denied，决策行 execution_status=NOT_EXECUTED
        追加 approval_outcome 事件行（step_no=100）。
        """
        action = str(action or "").lower()
        if action not in ("approve", "deny"):
            return {"ok": False, "error": "action must be approve or deny"}
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM audit_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": f"approval not found: {approval_id}"}
            status = row["status"]
            if status != "pending":
                return {
                    "ok": False,
                    "error": f"approval already resolved: {status}",
                }
            call_id = row["call_id"]
            session_id = row["session_id"]
            chain_id = row["chain_id"]
            tool_name = row["tool_name"]
            tool_params = row["tool_params"]
            policy_id = row["policy_id"]
            risk_score = row["risk_score"]
            risk_level = row["risk_level"]
            now = self._now()
            new_status = "approved" if action == "approve" else "denied"
            exec_status = (
                STATUS_EXECUTED if action == "approve" else STATUS_NOT_EXECUTED
            )
            drow = conn.execute(
                """SELECT event_uuid FROM security_events
                   WHERE call_id=? AND step_no=90 ORDER BY id DESC LIMIT 1""",
                (call_id,),
            ).fetchone()
            decision_event_uuid = drow["event_uuid"] if drow else None
            conn.execute(
                """UPDATE audit_approvals
                   SET status=?, decided_at=?, reviewer=?, decision_comment=?,
                       execution_status=?, event_uuid=?
                   WHERE approval_id=?""",
                (new_status, now, reviewer, comment, exec_status,
                 decision_event_uuid, approval_id),
            )
            conn.execute(
                """UPDATE security_events
                   SET execution_status=?, reviewer=?, decided_at=?
                   WHERE call_id=? AND step_no=90""",
                (exec_status, reviewer, now, call_id),
            )
            conn.execute(
                """UPDATE audit_calls
                   SET execution_status=?, ended_at=?
                   WHERE call_id=?""",
                (exec_status, now, call_id),
            )
            conn.commit()

        self.log_check(
            session_id=session_id,
            check_type="approval",
            tool_name=tool_name,
            tool_params=(
                json.loads(tool_params) if tool_params else None
            ),
            risk_score=float(risk_score or 0.0),
            risk_level=risk_level or "LOW",
            disposition=action,
            details={
                "approval_id": approval_id,
                "action": action,
                "reviewer": reviewer,
                "comment": comment,
                "call_id": call_id,
            },
            event_type=EVENT_APPROVAL_OUTCOME,
            policy_id=policy_id or "",
            decision_reason=comment or ("审批通过" if action == "approve" else "审批拒绝"),
            defense_stage="approval",
            call_id=call_id,
            chain_id=chain_id or self.chain_id_for_session(session_id),
            step_no=100,
            approval_id=approval_id,
            trigger_event_id=decision_event_uuid,
            execution_status=exec_status,
            reviewer=reviewer,
            decided_at=now,
        )
        return {
            "ok": True,
            "approval_id": approval_id,
            "status": new_status,
            "execution_status": exec_status,
            "call_id": call_id,
        }

    def log_execution_outcome(
        self,
        call_id: str,
        executed: bool,
        error: str = "",
        duration_ms: float = None,
    ) -> Dict[str, Any]:
        """
        上报一次工具调用的真实执行结果。

        - 执行成功      → EXECUTED
        - 执行失败/有错 → EXECUTION_ERROR
        - 未执行（阻断/拒绝）→ NOT_EXECUTED
        同步更新决策行与审批行终态，并追加 execution_outcome 事件行（step_no=110）。
        """
        executed = bool(executed)
        now = self._now()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM security_events
                   WHERE call_id=? AND step_no=90
                   ORDER BY id DESC LIMIT 1""",
                (call_id,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """SELECT * FROM security_events
                       WHERE call_id=? ORDER BY id LIMIT 1""",
                    (call_id,),
                ).fetchone()
            if row is None:
                return {"ok": False, "error": f"call not found: {call_id}"}
            session_id = row["session_id"]
            chain_id = row["chain_id"]
            tool_name = row["tool_name"]
            policy_id = row["policy_id"]
            risk_score = row["risk_score"]
            risk_level = row["risk_level"]
            decision_event_uuid = row["event_uuid"]
            if error:
                exec_status = STATUS_EXECUTION_ERROR
            else:
                exec_status = (
                    STATUS_EXECUTED if executed else STATUS_NOT_EXECUTED
                )
            conn.execute(
                """UPDATE security_events
                   SET execution_status=?, executed_at=?, tool_error=?
                   WHERE call_id=? AND step_no=90""",
                (exec_status, now, error or None, call_id),
            )
            conn.execute(
                "UPDATE audit_approvals SET execution_status=? WHERE call_id=?",
                (exec_status, call_id),
            )
            conn.execute(
                """UPDATE audit_calls
                   SET execution_status=?, ended_at=?
                   WHERE call_id=?""",
                (exec_status, now, call_id),
            )
            conn.commit()

        disposition = (
            "executed"
            if executed and not error
            else ("error" if error else "not_executed")
        )
        self.log_check(
            session_id=session_id,
            check_type="execution",
            tool_name=tool_name,
            risk_score=float(risk_score or 0.0),
            risk_level=risk_level or "LOW",
            disposition=disposition,
            details={
                "call_id": call_id,
                "executed": executed,
                "error": error or "",
                "duration_ms": duration_ms,
            },
            event_type=EVENT_EXECUTION_OUTCOME,
            policy_id=policy_id or "",
            decision_reason=error or ("工具已执行" if executed else "工具未执行"),
            defense_stage="execution",
            call_id=call_id,
            trigger_event_id=decision_event_uuid,
            chain_id=chain_id or self.chain_id_for_session(session_id),
            step_no=110,
            execution_status=exec_status,
            executed_at=now,
            tool_error=error or "",
        )
        return {"ok": True, "call_id": call_id, "execution_status": exec_status}

    # ---------------- 工具调用上下文 ----------------

    def open_call(self, session_id: str,
                  plugin_tool_call_id: str = None) -> str:
        """开启一次工具调用上下文，生成并绑定 call_id（同一调用的事件行共享）。"""
        call_id = self._new_call_id()
        chain_id = self.chain_id_for_session(session_id)
        now = self._now()
        self._ensure_session_and_chain(session_id, chain_id, now)
        _ACTIVE_CALL.set({
            "session_id": session_id,
            "call_id": call_id,
            "chain_id": chain_id,
            "plugin_tool_call_id": plugin_tool_call_id,
            "last_event_uuid": None,
        })
        return call_id

    def clear_call(self) -> None:
        """清除当前线程的工具调用上下文（输入/输出检测等非调用场景使用）。"""
        _ACTIVE_CALL.set(None)

    def new_call_id(self) -> str:
        """生成一个独立 call_id（不绑定上下文）。"""
        return self._new_call_id()

    def new_event_uuid(self) -> str:
        """生成一个独立 event_uuid。"""
        return self._new_event_uuid()

    # ---------------- 因果 / 薄聚合（Phase1 结构化攻击链） ----------------

    def _resolve_trigger_event(self, session_id, event_type, check_type,
                               defense_stage, disposition, step_no,
                               details, risk_score):
        """按业务规则显式确定 trigger_event_id（不依赖物理行序）。"""
        if not session_id:
            return None
        anchors = self._session_anchor.get(session_id) or {}
        decision_anchor = self._session_decision.get(session_id) or {}

        if step_no in (100, 110):
            # 审批/执行结果：调用方显式传 trigger；此处兜底取最近决策
            return decision_anchor.get("event_uuid")
        if event_type == "asset_resolved":
            return self._anchor_uuid(anchors, ("input",))
        if event_type == "data_classified":
            return self._anchor_uuid(anchors, ("asset",))
        if event_type in ("decoy_virtual_hit", "decoy_route_triggered",
                          "decoy.deployment_missing"):
            return self._anchor_uuid(anchors, ("asset", "decoy_hint", "data"))
        if event_type == "data_provenance_injected":
            return self._anchor_uuid(anchors, ("decoy_route", "asset", "data"))
        if event_type == "data_provenance_leak_detected":
            return self._anchor_uuid(anchors, ("dpt_inject", "decoy_route"))
        if event_type == "permission_violation":
            return self._anchor_uuid(anchors, ("behavior", "asset", "data"))
        if step_no == 90 and disposition in ("block", "kill", "review"):
            # 决策：优先“上一决策”锚点（如 read 后 upload），其次本调用风险锚点
            if decision_anchor.get("event_uuid"):
                return decision_anchor["event_uuid"]
            return self._anchor_uuid(
                anchors,
                ("dpt_inject", "dpt_leak", "decoy_route", "decoy_hint",
                 "behavior", "data", "asset", "input"),
            )
        return None

    @staticmethod
    def _anchor_uuid(anchors, priority):
        for kind in priority:
            hit = anchors.get(kind)
            if hit and hit.get("event_uuid"):
                return hit["event_uuid"]
        return None

    def _housekeep_after_event(self, session_id, call_id, chain_id,
                               event_uuid, event_type, step_no, disposition,
                               risk_score, risk_level, execution_status,
                               decision_reason, details, timestamp):
        """事件落库后的内存锚点 / 薄聚合维护（失败不影响事件写入）。"""
        try:
            if not event_uuid:
                return
            active = _ACTIVE_CALL.get()
            if active and call_id and call_id == active.get("call_id"):
                active["last_event_uuid"] = event_uuid
            if session_id:
                kind = _ANCHOR_BY_EVENT.get(event_type or "")
                if kind == "input" and risk_score <= 0:
                    kind = None
                if kind:
                    self._session_anchor.setdefault(session_id, {})[kind] = {
                        "event_uuid": event_uuid,
                        "risk": risk_score,
                    }
            if step_no == 90 and call_id:
                self._on_decision_event(
                    session_id=session_id, call_id=call_id, chain_id=chain_id,
                    event_uuid=event_uuid, event_type=event_type or "",
                    disposition=disposition, risk_score=risk_score,
                    risk_level=risk_level,
                    execution_status=execution_status,
                    decision_reason=decision_reason,
                    details=details or {}, timestamp=timestamp,
                )
        except Exception as exc:  # pragma: no cover
            print(f"[SecurityLogger] housekeeping warning: {exc}")

    def _on_decision_event(self, session_id, call_id, chain_id, event_uuid,
                           event_type, disposition, risk_score, risk_level,
                           execution_status, decision_reason, details,
                           timestamp):
        prev = self._session_decision.get(session_id)
        if prev and prev.get("event_uuid"):
            from_score = float(prev.get("risk", 0.0) or 0.0)
            to_score = float(risk_score or 0.0)
            cur_rank = _DISPOSITION_RANK.get(str(disposition), 0)
            prev_rank = _DISPOSITION_RANK.get(
                str(prev.get("disposition", "allow")), 0
            )
            if to_score > from_score + 1e-9 or cur_rank > prev_rank:
                self._write_escalation(
                    chain_id=chain_id, call_id=call_id,
                    from_event_uuid=prev["event_uuid"],
                    to_event_uuid=event_uuid,
                    from_score=from_score, to_score=to_score,
                    dominant_dimension=self._dominant_dimension(details),
                    trigger_reason=decision_reason,
                    decision=disposition, timestamp=timestamp,
                )
        self._session_decision[session_id] = {
            "event_uuid": event_uuid,
            "risk": float(risk_score or 0.0),
            "level": risk_level,
            "disposition": disposition,
        }
        chain_type = self._chain_type_for_decision(event_type, disposition, details)
        ended = timestamp if disposition in ("block", "kill") else None
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT call_id FROM audit_calls WHERE call_id = ?",
                    (call_id,),
                ).fetchone()
                if exists is None:
                    first = conn.execute(
                        """SELECT tool_name, timestamp FROM security_events
                           WHERE call_id = ? ORDER BY id LIMIT 1""",
                        (call_id,),
                    ).fetchone()
                    seq = conn.execute(
                        "SELECT COUNT(*) AS c FROM audit_calls WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()["c"]
                    conn.execute(
                        """INSERT INTO audit_calls
                           (call_id, session_id, chain_id, seq_no, tool_name,
                            started_at, ended_at, decision, execution_status)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (call_id, session_id, chain_id, seq + 1,
                         first["tool_name"] if first else "",
                         first["timestamp"] if first else timestamp,
                         ended, disposition, execution_status),
                    )
                else:
                    conn.execute(
                        """UPDATE audit_calls
                           SET decision=?, execution_status=?,
                               ended_at=COALESCE(?, ended_at)
                           WHERE call_id = ?""",
                        (disposition, execution_status, ended, call_id),
                    )
                conn.execute(
                    """UPDATE audit_chains
                       SET final_risk=?, final_disposition=?, chain_type=?,
                           status='open'
                       WHERE chain_id = ?""",
                    (float(risk_score or 0.0), disposition, chain_type, chain_id),
                )
                conn.commit()
        except sqlite3.Error as exc:  # pragma: no cover
            print(f"[SecurityLogger] decision aggregate warning: {exc}")

    @staticmethod
    def _chain_type_for_decision(event_type, disposition, details):
        if event_type == "prompt_injection":
            return "prompt_injection"
        if event_type == "data_exfiltration":
            return "data_exfiltration"
        if event_type == "permission_violation":
            return "permission"
        if event_type == "behavior_chain":
            sig = (
                ((details.get("behavior") or {}).get("behavior_signal") or {})
                .get("pattern", "")
            )
            if "EXFIL" in sig:
                return "data_exfiltration"
            if sig == "CRITICAL_ASSET_ACCESS":
                return "critical_asset"
            if sig == "HIGH_ASSET_ACCESS":
                return "high_asset"
            return "behavior_chain"
        if event_type == "data_provenance_leak_detected":
            return "dpt_leak"
        return "session"

    @staticmethod
    def _dominant_dimension(details):
        dims = (details or {}).get("dimensions") or {}
        if not dims:
            return ""
        return max(dims, key=lambda k: float(dims.get(k) or 0.0))

    def _write_escalation(self, chain_id, call_id, from_event_uuid,
                          to_event_uuid, from_score, to_score,
                          dominant_dimension, trigger_reason, decision,
                          timestamp):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO risk_escalations
                   (chain_id, call_id, from_event_uuid, to_event_uuid,
                    from_score, to_score, delta, dominant_dimension,
                    trigger_reason, decision, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (chain_id, call_id, from_event_uuid, to_event_uuid,
                 round(float(from_score), 3), round(float(to_score), 3),
                 round(float(to_score) - float(from_score), 3),
                 dominant_dimension, trigger_reason, decision, timestamp),
            )
            conn.commit()

    def _ensure_session_and_chain(self, session_id, chain_id, timestamp):
        if not session_id or not chain_id:
            return
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO audit_sessions
                       (session_id, started_at, status) VALUES (?,?,?)""",
                    (session_id, timestamp, "open"),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO audit_chains
                       (chain_id, session_id, chain_type, started_at, status)
                       VALUES (?,?,?,?,?)""",
                    (chain_id, session_id, "session", timestamp, "open"),
                )
                conn.commit()
        except sqlite3.Error as exc:  # pragma: no cover
            print(f"[SecurityLogger] session/chain seed warning: {exc}")

    # ---------------- 查询 ----------------

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

    def get_chain(self, session_id: str) -> Dict[str, Any]:
        """获取指定会话的完整审计链（按写入顺序）。"""
        chain_id = self.chain_id_for_session(session_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if chain_id:
                rows = conn.execute(
                    """SELECT * FROM security_events
                       WHERE session_id = ? OR chain_id = ?
                       ORDER BY id ASC""",
                    (session_id, chain_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM security_events WHERE session_id = ? ORDER BY id ASC",
                    (session_id,),
                ).fetchall()
            return {
                "session_id": session_id,
                "chain_id": chain_id,
                "total_events": len(rows),
                "events": [dict(r) for r in rows],
            }

    def get_call(self, call_id: str) -> Dict[str, Any]:
        """获取一次工具调用的全部证据（决策 + 子步骤 + 审批 + 执行结果）。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM security_events
                   WHERE call_id = ? ORDER BY step_no ASC, id ASC""",
                (call_id,),
            ).fetchall()
            events = [dict(r) for r in rows]
            decision = next(
                (e for e in events if e.get("step_no") == 90), None
            )
            approval = None
            if decision and decision.get("approval_id"):
                ar = conn.execute(
                    "SELECT * FROM audit_approvals WHERE approval_id = ?",
                    (decision["approval_id"],),
                ).fetchone()
                approval = dict(ar) if ar else None
            return {
                "call_id": call_id,
                "decision": decision,
                "approval": approval,
                "events": events,
            }

    def get_escalations(self, session_id: str = None,
                        chain_id: str = None, limit: int = 200) -> list:
        """获取风险升级记录（按 chain/session）。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if chain_id:
                rows = conn.execute(
                    """SELECT * FROM risk_escalations
                       WHERE chain_id = ? ORDER BY escalation_id ASC LIMIT ?""",
                    (chain_id, limit),
                ).fetchall()
            elif session_id:
                cid = self.chain_id_for_session(session_id)
                rows = conn.execute(
                    """SELECT * FROM risk_escalations
                       WHERE chain_id = ? ORDER BY escalation_id ASC LIMIT ?""",
                    (cid, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM risk_escalations
                       ORDER BY escalation_id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_audit_tree(self, session_id: str) -> Dict[str, Any]:
        """按 session 组装 Session→Chain→Call→Event 树，含因果路径与升级记录。"""
        chain_id = self.chain_id_for_session(session_id)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            srow = conn.execute(
                "SELECT * FROM audit_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            crow = conn.execute(
                "SELECT * FROM audit_chains WHERE chain_id = ?",
                (chain_id,),
            ).fetchone()
            if chain_id:
                rows = conn.execute(
                    """SELECT * FROM security_events
                       WHERE session_id = ? OR chain_id = ? ORDER BY id ASC""",
                    (session_id, chain_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM security_events WHERE session_id = ? ORDER BY id ASC",
                    (session_id,),
                ).fetchall()
            escal_rows = conn.execute(
                "SELECT * FROM risk_escalations WHERE chain_id = ? ORDER BY escalation_id ASC",
                (chain_id,),
            ).fetchall()
        events = [dict(r) for r in rows]
        escal = [dict(r) for r in escal_rows]
        ev_by_uuid = {e.get("event_uuid"): e for e in events if e.get("event_uuid")}
        groups, uncalled = {}, []
        for e in events:
            cid = e.get("call_id")
            (groups.setdefault(cid, []).append(e) if cid else uncalled.append(e))

        def causal_path(decision_event):
            path, seen = [], set()
            node = decision_event
            while node and node.get("event_uuid") and node["event_uuid"] not in seen:
                seen.add(node["event_uuid"])
                path.append(node)
                nxt = node.get("trigger_event_id") or node.get("parent_event_id")
                node = ev_by_uuid.get(nxt) if nxt else None
            path.sort(key=lambda n: (n.get("id") or 0))
            return [{
                "event_uuid": x.get("event_uuid"),
                "event_type": x.get("event_type") or x.get("check_type"),
                "disposition": x.get("disposition"),
                "risk_score": x.get("risk_score"),
                "risk_level": x.get("risk_level"),
                "step_no": x.get("step_no"),
                "call_id": x.get("call_id"),
                "tool_name": x.get("tool_name"),
            } for x in path]

        calls = []
        for cid in sorted(
            groups, key=lambda c: min((e.get("id") or 0) for e in groups[c])
        ):
            evs = sorted(
                groups[cid],
                key=lambda e: (e.get("step_no") or 0, e.get("id") or 0),
            )
            decision = next((x for x in evs if x.get("step_no") == 90), None)
            approval = None
            if decision and decision.get("approval_id"):
                approval = self.get_approval(decision["approval_id"])
            calls.append({
                "call_id": cid,
                "tool_name": (decision or evs[0]).get("tool_name", ""),
                "decision": decision,
                "approval": approval,
                "execution_status": (decision or {}).get("execution_status"),
                "events": evs,
                "escalations": [x for x in escal if x.get("call_id") == cid],
                "causal_path": causal_path(decision) if decision else [],
            })
        return {
            "session_id": session_id,
            "session": dict(srow) if srow else None,
            "chain": dict(crow) if crow else None,
            "chain_id": chain_id,
            "escalations": escal,
            "calls": calls,
            "uncalled_events": uncalled,
            "total_events": len(events),
        }

    def get_approval(self, approval_id: str) -> Optional[dict]:
        """获取单条审批记录。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM audit_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_pending_approvals(self, limit: int = 100) -> list:
        """获取所有待审批记录。"""
        return self.get_approvals(status="pending", limit=limit)

    def get_approvals(self, status: str = None, limit: int = 200) -> list:
        """获取审批记录列表。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    """SELECT * FROM audit_approvals
                       WHERE status = ? ORDER BY requested_at DESC LIMIT ?""",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM audit_approvals
                       ORDER BY requested_at DESC LIMIT ?""",
                    (limit,),
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
