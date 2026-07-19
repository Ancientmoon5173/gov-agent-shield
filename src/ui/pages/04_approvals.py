
"""
审批管理页面。
连接 ApprovalManager，支持查看、审批、拒绝。
"""

import streamlit as st

st.set_page_config(page_title="审批管理 - GovAgent-Shield SOC", layout="wide")

st.title("📝 审批管理")
st.caption("管理高风险操作的审批请求")

from src.ui.data_provider import get_orchestrator

orc = get_orchestrator()
approval_mgr = orc.permission_checker._core.approval_manager

# ========================
# Pending Approvals
# ========================
st.subheader("待审批请求")
pending = approval_mgr.get_pending()

if pending:
    for req in pending:
        with st.container(border=True):
            cols = st.columns([2, 2, 2, 1, 1])
            cols[0].markdown(f"**{req.get('agent_id', '?')}**")
            cols[1].markdown(f"`{req.get('tool_name', '?')}`")
            cols[2].markdown(f"{req.get('reason', '')}")
            cols[3].markdown(f"📅 {str(req.get('created_at', ''))[11:19] if req.get('created_at') else ''}")

            btn_cols = cols[4].columns(2)
            if btn_cols[0].button("✅", key=f"approve_{req['id']}"):
                approval_mgr.approve(req["id"])
                st.rerun()
            if btn_cols[1].button("❌", key=f"reject_{req['id']}"):
                approval_mgr.reject(req["id"])
                st.rerun()
else:
    st.success("无待审批请求。")

# ========================
# Approval History
# ========================
st.subheader("审批记录")
all_approvals = approval_mgr.get_all()
resolved = [a for a in all_approvals if a.get("status") != "pending"]

if resolved:
    rows = []
    for a in resolved:
        rows.append({
            "ID": a.get("id", ""),
            "Agent": a.get("agent_id", ""),
            "工具": a.get("tool_name", ""),
            "状态": a.get("status", ""),
            "创建时间": str(a.get("created_at", ""))[11:19] if a.get("created_at") else "",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("暂无已处理的审批记录。")
