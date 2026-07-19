
"""
任务监控页面。
展示安全日志记录器中的事件，支持筛选和搜索。
"""

import streamlit as st

st.set_page_config(page_title="任务监控 - GovAgent-Shield SOC", layout="wide")

from src.ui.data_provider import get_logger

logger = get_logger()

st.title("📋 实时任务监控")
st.caption("查看所有 Agent 工具调用的安全检测记录")

# ========================
# Filters
# ========================
col1, col2, col3 = st.columns(3)
with col1:
    level_filter = st.multiselect(
        "风险等级",
        ["LOW", "MEDIUM", "HIGH", "VERY_HIGH", "CRITICAL"],
        default=[],
    )
with col2:
    action_filter = st.multiselect(
        "处置动作",
        ["allow", "warn", "review", "block", "kill"],
        default=[],
    )
with col3:
    st.markdown("### 刷新")
    st.button("🔄 刷新数据")

# ========================
# Event Table
# ========================
events = logger.get_recent_events(200)

# Apply filters
if level_filter:
    events = [e for e in events if e.get("risk_level") in level_filter]
if action_filter:
    events = [e for e in events if e.get("disposition") in action_filter]

if events:
    rows = []
    for e in events:
        rows.append({
            "时间": str(e.get("timestamp", ""))[11:19] if e.get("timestamp") else "",
            "会话": str(e.get("session_id", ""))[:12],
            "检测类型": e.get("check_type", ""),
            "工具": str(e.get("tool_name", ""))[:20],
            "风险评分": e.get("risk_score", 0),
            "风险等级": e.get("risk_level", "LOW"),
            "处置": e.get("disposition", "allow"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"显示 {len(rows)} 条记录")
else:
    st.info("暂无匹配事件。")
