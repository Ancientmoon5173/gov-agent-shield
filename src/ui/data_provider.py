
"""
UI 数据提供器。

使用 Streamlit cache 保持跨页面数据一致性。
调用者不需要直接创建安全模块实例。
"""

import streamlit as st


@st.cache_resource
def get_logger():
    """获取安全日志记录器（缓存）。"""
    from src.security.security_logger import create_security_logger
    return create_security_logger()


@st.cache_resource
def get_permission_storage():
    """获取权限存储（缓存）。"""
    from src.permission.storage import create_permission_storage
    return create_permission_storage()


@st.cache_resource
def get_orchestrator():
    """获取安全协调器（缓存）。"""
    from src.security import create_orchestrator
    return create_orchestrator()


@st.cache_resource
def get_decoy_registry():
    """获取诱饵注册表（缓存）。"""
    orc = get_orchestrator()
    return orc.decoy_manager.registry if orc.decoy_manager.is_initialized else []


def load_demo_data():
    """加载演示数据（运行 5 个 Demo 场景产生日志）。"""
    from samples.attack_scenarios import run_scenario_demo
    run_scenario_demo()
    return True
