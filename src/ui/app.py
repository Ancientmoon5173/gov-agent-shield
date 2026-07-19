
"""
GovAgent-Shield 安全运营中心

启动方式: streamlit run src/ui/app.py

功能：
- Dashboard: 系统概览
- 任务监控: 实时事件日志
- 安全事件: 分类攻击展示
- 权限管理: Agent 权限配置
- 审批管理: 审批流程
"""

import streamlit as st

st.set_page_config(
    page_title="GovAgent-Shield SOC",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========================
# Sidebar
# ========================
st.sidebar.markdown("## 🛡️ GovAgent-Shield")
st.sidebar.markdown("安全运营中心")
st.sidebar.divider()

# Load demo data on first run
if "demo_loaded" not in st.session_state:
    st.session_state.demo_loaded = False


def load_demo():
    """加载演示数据。"""
    from src.ui.data_provider import load_demo_data
    with st.spinner("加载演示数据..."):
        load_demo_data()
    st.session_state.demo_loaded = True
    st.rerun()


if not st.session_state.demo_loaded:
    st.sidebar.button("🚀 加载演示数据", on_click=load_demo, type="primary")
st.sidebar.divider()

# ========================
# Page routing
# ========================
# Streamlit multi-page handles routing via pages/*.py
# This file serves as the landing page (Dashboard).

from src.ui.data_provider import get_logger, get_permission_storage

logger = get_logger()
summary = logger.get_summary()
events = logger.get_recent_events(20)
perm_storage = get_permission_storage()
agents = perm_storage.list_agents()

# ========================
# Header
# ========================
st.title("🛡️ GovAgent-Shield 安全运营中心")
st.caption("面向政企场景的大模型智能体安全防护平台")

# ========================
# Metric Cards
# ========================
col1, col2, col3, col4 = st.columns(4)

total = summary.get("total_events", 0)
blocked = summary.get("disposition_counts", {}).get("block", 0)
critical = summary.get("level_distribution", {}).get("CRITICAL", 0)
pending = 0

# Count pending approvals
try:
    from src.ui.data_provider import get_orchestrator
    orc = get_orchestrator()
    pending = len(orc.permission_checker._core.approval_manager.get_pending())
except Exception:
    pass

col1.metric("总安全事件", total, delta=None)
col2.metric("阻断事件", blocked, delta=None, delta_color="inverse")
col3.metric("严重告警", critical, delta=None, delta_color="inverse")
col4.metric("待审批", pending, delta=None)

# ========================
# Recent Events
# ========================
st.subheader("最近安全事件")

if events:
    rows = []
    for e in events:
        rows.append({
            "时间": str(e.get("timestamp", ""))[11:19] if e.get("timestamp") else "",
            "类型": e.get("check_type", ""),
            "工具": str(e.get("tool_name", ""))[:20],
            "评分": e.get("risk_score", 0),
            "等级": e.get("risk_level", ""),
            "处置": e.get("disposition", ""),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("暂无安全事件。点击左侧「加载演示数据」生成示例数据。")

# ========================
# Agent Status
# ========================
st.subheader("Agent 状态")
if agents:
    for agent in agents:
        tools = agent.get("allowed_tools", [])
        restrict = agent.get("restricted_tools", [])
        tools_str = ", ".join(tools[:5])
        restrict_str = ", ".join(restrict) if restrict else "无"
        with st.expander(f"{agent.get('id', '?')} ({agent.get('role', '?')})"):
            col1, col2 = st.columns(2)
            col1.markdown(f"**允许工具:** {tools_str}")
            col2.markdown(f"**禁止工具:** {restrict_str}")
else:
    st.info("未配置 Agent 权限。")
