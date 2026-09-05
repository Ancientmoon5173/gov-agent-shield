import sys
from pathlib import Path

# Streamlit 启动时可能不包含项目根目录，这里显式自举，保证 src.* 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

"""
审计回放页面（V1 + Phase1）。

- 输入 session_id → 展示 Session→Chain→Call→Event 证据链（平铺时间线）
- 每个 Call 折叠展示步骤事件 + 审批 + 执行结果
- 因果链视图：通过 trigger_event_id / parent_event_id 反向回答“为什么最终 BLOCK/KILL”
- 风险升级记录：from→to / delta / dominant dimension
- 表格与状态值中英双语展示
"""

import json

import streamlit as st

from src.ui._page_config import safe_set_page_config

safe_set_page_config(page_title="审计回放 - GovAgent-Shield SOC", layout="wide")

from src.ui.data_provider import fmt_time, get_audit_logger

logger = get_audit_logger()

EVENT_ZH = {
    "asset_resolved": "资产识别",
    "data_classified": "数据分级",
    "decoy_virtual_hit": "诱饵观察",
    "decoy_event": "诱饵触碰",
    "decoy_route_triggered": "诱饵路由",
    "decoy.deployment_missing": "诱饵部署缺失",
    "data_provenance_injected": "令牌注入",
    "data_provenance_leak_detected": "令牌外泄",
    "permission_violation": "权限/越权",
    "behavior_chain": "行为链",
    "tool_risk": "工具风险",
    "prompt_injection": "提示注入",
    "input_risk": "输入风险",
    "data_exfiltration": "数据外传",
    "approval_outcome": "审批结果",
    "execution_outcome": "执行结果",
}

STATUS_ZH = {
    "EXECUTED": "已执行",
    "NOT_EXECUTED": "未执行",
    "PENDING_APPROVAL": "待审批",
    "PENDING_EXECUTION": "待执行",
    "EXECUTION_ERROR": "执行异常",
    "APPROVED": "已通过",
    "DENIED": "已拒绝",
    "BLOCKED": "已阻断",
}


def ev_zh(value):
    if not value:
        return ""
    name = EVENT_ZH.get(value, "")
    return f"{value}（{name}）" if name else value


def status_zh(value):
    if not value:
        return ""
    name = STATUS_ZH.get(value, "")
    return f"{value}（{name}）" if name else value


def _brief(e):
    details = e.get("details")
    if isinstance(details, str) and details:
        try:
            return json.loads(details)
        except json.JSONDecodeError:
            return {"raw": details[:100]}
    return details or {}


st.title("🕵️ 审计回放（证据链 / 因果链）")
st.caption("按 session 还原：识别 → 行为 → 风险升级 → 决策 → 审批 → 执行 的完整链路")
st.caption("证据链检索指标：session_id（一级链路主键）→ call_id（单次工具调用）→ step_no（步骤）；"
           "chain_id 由 session_id 派生；因果链由 trigger_event_id / parent_event_id 显式关联，"
           "可回答“为什么最终 BLOCK/KILL”")

recent = logger.get_recent_events(300)
sessions, seen = [], set()
for e in recent:
    sid = e.get("session_id")
    if sid and sid not in seen:
        seen.add(sid)
        sessions.append(sid)

default_session = sessions[0] if sessions else ""
session_id = st.text_input("会话 ID（session_id）", value=default_session)
search = st.button("🔍 查询证据链")

if search and session_id:
    tree = logger.get_audit_tree(session_id)
    if not tree.get("total_events"):
        st.warning("该会话暂无审计记录。")
    else:
        chain = tree.get("chain") or {}
        st.caption(
            f"chain_id: `{tree.get('chain_id')}` | chain_type: {chain.get('chain_type', 'session')} | "
            f"final: {chain.get('final_disposition')} @ {chain.get('final_risk')} | "
            f"状态: {chain.get('status', 'open')}（未收到 session-end 信号） | 事件总数: {tree.get('total_events')}"
        )

        # ============ 因果链 / 风险升级总览 ============
        st.subheader("⚡ 因果链与风险升级")
        kill_calls = [c for c in tree.get("calls", [])
                      if (c.get("decision") or {}).get("disposition") in ("block", "kill")]
        if kill_calls or tree.get("escalations"):
            for c in tree["calls"]:
                dec = c.get("decision") or {}
                path = c.get("causal_path") or []
                if len(path) >= 2:
                    why = "为什么" if dec.get("disposition") in ("allow", "warn") else (
                        "为什么最终 " + str(dec.get("disposition", "")).upper())
                    with st.expander(
                        f"🔗 {why}：{dec.get('disposition', '')} {c.get('tool_name')} "
                        f"(Call {c.get('call_id')})", expanded=False
                    ):
                        lines = []
                        for i, p in enumerate(path):
                            arrow = " → " if i < len(path) - 1 else ""
                            lines.append(
                                f"{p.get('event_type') and ev_zh(p.get('event_type')) or p.get('event_type')}"
                                f" [{p.get('disposition')}] risk={p.get('risk_score')} {p.get('risk_level')}"
                                f"{arrow}"
                            )
                        st.markdown(" ".join(lines))
                        st.caption("以上按 trigger_event_id / parent_event_id 反向追溯到最初触发事件。")
            if tree.get("escalations"):
                esc_rows = [{
                    "风险升级": f"{e['from_score']} → {e['to_score']} (Δ{e['delta']})",
                    "主导维度": e.get("dominant_dimension", ""),
                    "触发决策": e.get("decision", ""),
                    "原因": str(e.get("trigger_reason", ""))[:80],
                    "时间": fmt_time(e.get("timestamp")),
                } for e in tree["escalations"]]
                st.dataframe(esc_rows, use_container_width=True, hide_index=True)
        else:
            st.info("该会话未出现 block/kill 决策，也没有风险升级记录。")

        # ============ Call 级证据 ============
        st.subheader("📄 Call 证据链（含会话ID溯源）")
        for c in tree.get("calls", []):
            dec = c.get("decision") or {}
            status = c.get("execution_status") or ""
            emoji = {
                "EXECUTED": "✅", "NOT_EXECUTED": "⛔", "PENDING_APPROVAL": "🕓",
                "PENDING_EXECUTION": "🔄", "EXECUTION_ERROR": "⚠️",
            }.get(status, "⚪")
            title = (
                f"{emoji} {c.get('call_id')} | tool: {c.get('tool_name', '?')} "
                f"| action: {dec.get('disposition', '')} | status: {status_zh(status)}"
            )
            with st.expander(title, expanded=False):
                st.caption(
                    f"会话ID: `{session_id}` | policy: {dec.get('policy_id', '')} | "
                    f"reason: {dec.get('decision_reason', '')}"
                )
                approval = c.get("approval")
                if approval:
                    st.markdown(
                        f"**审批**: `{approval.get('approval_id')}` → {approval.get('status')} | "
                        f"执行终态 {status_zh(approval.get('execution_status'))} | "
                        f"审批人 {approval.get('reviewer')} | 会话ID `{approval.get('session_id')}`"
                    )
                rows = []
                for e in c.get("events", []):
                    rows.append({
                        "step": e.get("step_no"),
                        "会话ID": str(e.get("session_id", "")),
                        "事件": ev_zh(e.get("event_type") or e.get("check_type")),
                        "风险": e.get("risk_score"),
                        "等级": e.get("risk_level"),
                        "处置": e.get("disposition"),
                        "状态": status_zh(e.get("execution_status")),
                        "父事件": (e.get("parent_event_id") or "")[:8],
                        "触发事件": (e.get("trigger_event_id") or "")[:8],
                        "detail": json.dumps(_brief(e), ensure_ascii=False)[:120],
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)

        if tree.get("uncalled_events"):
            with st.expander("非调用事件（输入/输出检测）", expanded=False):
                unc_rows = [{
                    "时间": fmt_time(e.get("timestamp")),
                    "会话ID": str(e.get("session_id", "")),
                    "事件": ev_zh(e.get("event_type") or e.get("check_type")),
                    "风险": e.get("risk_score"),
                    "等级": e.get("risk_level"),
                    "处置": e.get("disposition"),
                } for e in tree["uncalled_events"]]
                st.dataframe(unc_rows, use_container_width=True, hide_index=True)
