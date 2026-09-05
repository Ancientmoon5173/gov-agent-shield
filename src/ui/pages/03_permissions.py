import sys
from pathlib import Path

# Streamlit 启动时可能不包含项目根目录，这里显式自举，保证 src.* 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


"""
权限管理页面。
展示 permissions.json 中的 Agent 权限配置。
"""

import streamlit as st

from src.ui._page_config import safe_set_page_config

safe_set_page_config(page_title="权限管理 - GovAgent-Shield SOC", layout="wide")

from src.ui.data_provider import get_permission_storage, get_orchestrator

st.title("🔐 权限管理")
st.caption("查看 Agent 角色和工具权限配置")

perm_storage = get_permission_storage()
agents = perm_storage.list_agents()
orchestrator = get_orchestrator()

# ========================
# Agent Permission Cards
# ========================
if agents:
    st.subheader(f"已配置 {len(agents)} 个 Agent")

    for agent in agents:
        with st.container(border=True):
            col1, col2, col3 = st.columns([1, 2, 1])
            col1.markdown(f"### {agent.get('id', '?')}")
            col2.markdown(f"**角色:** {agent.get('role', '?')}")
            col3.markdown(f"**工具数:** {len(agent.get('allowed_tools', []))}")

            tabs = st.tabs(["✅ 允许工具", "🚫 禁止工具", "📋 需审批"])
            with tabs[0]:
                tools = agent.get("allowed_tools", [])
                if tools:
                    st.markdown("、".join(f"`{t}`" for t in tools))
                else:
                    st.info("无允许工具（将被完全限制）")
            with tabs[1]:
                restricted = agent.get("restricted_tools", [])
                if restricted:
                    st.markdown("、".join(f"`{r}`" for r in restricted))
                else:
                    st.success("无不禁止工具")
            with tabs[2]:
                approval = agent.get("require_approval", [])
                if approval:
                    st.markdown("、".join(f"`{a}`" for a in approval))
                else:
                    st.success("无需审批")
else:
    st.warning("未找到权限配置。请确认 data/permissions.json 存在。")

# ========================
# Decoy Registry
# ========================
st.subheader("🎯 诱饵资源")
decoy_list = orchestrator.decoy_manager.registry
if decoy_list:
    for d in decoy_list:
        level = d.get("level", "LOW")
        emoji = {"HIGH": "🟡", "CRITICAL": "🔴"}.get(level, "🟢")
        st.markdown(f"{emoji} `{d.get('path', '?')}` ({d.get('type', '?')}) 等级: {level}")
else:
    st.info("未生成诱饵资源。")
