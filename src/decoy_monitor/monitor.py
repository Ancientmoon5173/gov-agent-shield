"""
诱饵监控器。
检查Agent的访问路径是否触碰了诱饵资源。
"""

from pathlib import Path
from typing import Dict, Any, Optional

class DecoyMonitor:
    """诱饵触碰监控器。"""
    def __init__(self, registry: list):
        self._registry = registry

    def check_access(self, path: str) -> Optional[Dict[str, Any]]:
        access_path = Path(path).resolve()
        for decoy in self._registry:
            decoy_path = Path(decoy["path"]).resolve()
            if decoy["type"] == "file" and access_path == decoy_path:
                return {"triggered": True, "decoy_path": str(decoy_path), "decoy_type": decoy["type"], "severity": decoy["level"], "detail": f"触发诱饵文件: {decoy_path.name}"}
            if decoy["type"] == "directory" and decoy_path in access_path.parents:
                return {"triggered": True, "decoy_path": str(decoy_path), "decoy_type": decoy["type"], "severity": decoy["level"], "detail": f"访问诱饵目录: {decoy_path.name}"}
        return None

    def check_paths(self, paths: list) -> list:
        return [p for p in (self.check_access(x) for x in paths) if p]

    @property
    def registry(self):
        return self._registry
