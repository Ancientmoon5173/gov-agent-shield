import sys
from pathlib import Path

# Streamlit 启动时可能不包含项目根目录，这里显式自举，保证 src.* 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

"""
审批管理页面（V1 闭环版 · 本地直连提速）。

数据源：SQLite audit_approvals（与引擎共享同一库）。
审批动作直接调用 SecurityLogger.resolve_approval 落库并追加审计事件
（不依赖引擎 HTTP，页面即时刷新）：
- 通过 → approved / EXECUTED
- 拒绝 → denied  / NOT_EXECUTED
"""

import json

import streamlit as st

from src.ui._page_config import safe_set_page_config

safe_set_page_config(page_title="审批管理 - GovAgent-Shield SOC", layout="wide")

from src.ui.data_provider import fmt_time, get_audit_logger

logger = get_audit_logger()

st.title("📝 审批管理（闭环）")
st.caption("高风险操作人工审批：通过 → EXECUTED；拒绝 → NOT_EXECUTED（本地 SQLite 直连，即时生效）")

# 操作反馈（跨 rerun 保留一次）
flash = st.session_state.pop("approval_flash", None)
if flash:
    st.success(flash)

# ========================
# 待审批请求
# ========================
st.subheader("待审批请求")
pending = logger.get_pending_approvals()

if pending:
    for req in pending:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 2, 3])
            c1.markdown(f"**{req.get('agent_id') or '-'}**")
            c2.markdown(f"`{req.get('tool_name')}`")
            c3.markdown(f"风险: **{req.get('risk_score')}** {req.get('risk_level')}")

            st.caption(
                f"审批ID: `{req['approval_id']}` | 会话ID: `{req.get('session_id')}` | "
                f"Call: `{req.get('call_id')}` | policy: {req.get('policy_id')}"
            )
            st.caption(
                f"请求时间: {fmt_time(req.get('requested_at'), with_seconds=True)} | "
                f"原因: {req.get('decision_reason') or ''}"
            )
            params = req.get("tool_params") or "{}"
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {"raw": params}
            st.code(json.dumps(params, ensure_ascii=False, indent=1)[:600], language="json")

            reviewer = st.text_input("审批人", key=f"reviewer_{req['approval_id']}")
            comment = st.text_input("审批意见（可选）", key=f"comment_{req['approval_id']}")

            def do_resolve(approval_id, action, reviewer, comment):
                result = logger.resolve_approval(
                    approval_id=approval_id,
                    action=action,
                    reviewer=reviewer or "soc-operator",
                    comment=comment,
                )
                return result

            b1, b2 = st.columns(2)
            if b1.button("✅ 通过", key=f"ok_{req['approval_id']}", type="primary"):
                result = do_resolve(req["approval_id"], "approve", reviewer, comment)
                if result.get("ok"):
                    st.session_state["approval_flash"] = (
                        f"✅ 已通过 `{req['approval_id']}`（会话 `{req.get('session_id')}`）"
                        f" → approved / EXECUTED"
                    )
                    st.rerun()
                else:
                    st.error(f"审批失败: {result.get('error')}")
            if b2.button("❌ 拒绝", key=f"no_{req['approval_id']}"):
                result = do_resolve(req["approval_id"], "deny", reviewer, comment)
                if result.get("ok"):
                    st.session_state["approval_flash"] = (
                        f"❌ 已拒绝 `{req['approval_id']}`（会话 `{req.get('session_id')}`）"
                        f" → denied / NOT_EXECUTED"
                    )
                    st.rerun()
                else:
                    st.error(f"审批失败: {result.get('error')}")
else:
    st.success("无待审批请求。")

# ========================
# 审批记录
# ========================
st.subheader("审批记录")
resolved = [a for a in logger.get_approvals() if a.get("status") != "pending"]
if resolved:
    rows = []
    for a in resolved[:200]:
        rows.append({
            "审批ID": a.get("approval_id", ""),
            "会话ID": str(a.get("session_id", "")),
            "Agent": a.get("agent_id", ""),
            "工具": a.get("tool_name", ""),
            "状态": a.get("status", ""),
            "执行终态": a.get("execution_status", ""),
            "审批人": a.get("reviewer", ""),
            "意见": str(a.get("decision_comment", ""))[:60],
            "请求时间": fmt_time(a.get("requested_at"), with_seconds=False),
            "审批时间": fmt_time(a.get("decided_at"), with_seconds=False),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("暂无已处理的审批记录。")
