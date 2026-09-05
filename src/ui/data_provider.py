import sys
from pathlib import Path

# Streamlit 启动时可能不包含项目根目录，这里显式自举，保证 src.* 可导入
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


"""
UI 数据提供器。

使用 Streamlit cache 保持跨页面数据一致性。
调用者不需要直接创建安全模块实例。
"""

import streamlit as st


import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

# 审计库时间统一按东八区（Asia/Shanghai）展示
_CST = timezone(timedelta(hours=8))


def fmt_time(value, with_seconds=True, default=""):
    """把审计库里的 UTC ISO 时间转换为东八区本地时间字符串。"""
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(_CST)
    return dt.strftime(
        "%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M"
    )


def get_audit_api_base() -> str:
    """引擎审计 API 地址（SOC 与引擎跨进程，审批写操作走引擎）。"""
    return os.getenv("GOVAGENT_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def audit_api_post(path: str, payload: dict) -> dict:
    """调用引擎审计写接口（POST）。"""
    url = get_audit_api_base() + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
def get_audit_logger():
    """审计日志记录器（V1 闭环：只读 SQLite，与引擎共享同一库）。"""
    from src.security.security_logger import SecurityLogger
    return SecurityLogger()


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
