
"""
安全事件页面。
按攻击类型分类展示安全事件。
"""

import streamlit as st

st.set_page_config(page_title="安全事件 - GovAgent-Shield SOC", layout="wide")

from src.ui.data_provider import get_logger

logger = get_logger()

st.title("🔴 安全事件分析")
st.caption("按攻击类型分类的安全事件视图")

events = logger.get_recent_events(500)

# ========================
# Tabbed view
# ========================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "全部事件", "诱饵触碰", "越权访问", "提示注入", "数据外传",
])


def filter_events(events, check_type=None, disposition=None, level=None):
    """过滤事件列表。"""
    result = events
    if check_type:
        result = [e for e in result if e.get("check_type") == check_type]
    if disposition:
        result = [e for e in result if e.get("disposition") in disposition]
    if level:
        result = [e for e in result if e.get("risk_level") in level]
    return result


def render_event_table(events):
    """渲染事件表格。"""
    if not events:
        st.info("暂无事件记录。")
        return

    rows = []
    for e in events[:50]:
        rows.append({
            "时间": str(e.get("timestamp", ""))[11:19] if e.get("timestamp") else "",
            "类型": e.get("check_type", ""),
            "工具": str(e.get("tool_name", ""))[:20],
            "评分": e.get("risk_score", 0),
            "等级": e.get("risk_level", "LOW"),
            "处置": e.get("disposition", ""),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"显示 {len(rows)} 条记录")


with tab1:
    render_event_table(events)

with tab2:
    decoy_events = filter_events(events, check_type="decoy_event")
    render_event_table(decoy_events)

with tab3:
    perm_events = filter_events(events, check_type="permission", disposition=["block"])
    render_event_table(perm_events)

with tab4:
    injection_events = filter_events(events, check_type="input", level=["HIGH", "VERY_HIGH", "CRITICAL"])
    render_event_table(injection_events)

with tab5:
    upload_events = filter_events(events, check_type="tool_call", disposition=["kill", "block"])
    render_event_table(upload_events)
