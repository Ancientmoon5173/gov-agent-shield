"""
权限存储模块。

从 permissions.json 加载权限策略，不做硬编码。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.config import DATA_DIR
from .models import PermissionPolicy


DEFAULT_PERMISSIONS_FILE = DATA_DIR / "permissions.json"


class PermissionStorage:
    """权限存储加载器。"""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or DEFAULT_PERMISSIONS_FILE
        self._cache: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """加载完整的权限配置文件。"""
        if self._cache is not None:
            return self._cache

        if not self.file_path.exists():
            return {"agents": [], "default_agent_id": "default_agent"}

        with open(self.file_path, encoding="utf-8") as f:
            self._cache = json.load(f)
        return self._cache

    def get_policy(self, agent_id: str) -> PermissionPolicy:
        """获取指定 Agent 的权限策略。"""
        data = self.load()
        agents = data.get("agents", [])

        for agent_data in agents:
            if agent_data.get("id") == agent_id:
                return PermissionPolicy.from_dict(agent_data)

        # 不存在时返回默认策略（空权限）
        return PermissionPolicy(agent_id=agent_id, role="unknown")

    def get_default_agent_id(self) -> str:
        """获取默认 Agent ID。"""
        data = self.load()
        return data.get("default_agent_id", "default_agent")

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent 权限信息。"""
        data = self.load()
        return data.get("agents", [])

    def reload(self) -> None:
        """重新加载权限配置（开发时修改 JSON 后调用）。"""
        self._cache = None


def create_permission_storage() -> PermissionStorage:
    """创建权限存储实例。"""
    return PermissionStorage()
