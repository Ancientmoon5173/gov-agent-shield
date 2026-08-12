"""
资产身份解析器（AssetResolver）。

将工具调用参数解析为资产身份标签：
asset_type / sensitivity / owner / policy，
供行为观察、诱饵路由与风险引擎使用。

资产目录来自 data/asset_catalog.json，避免纯路径关键词散落代码。
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config import ASSET_CATALOG_PATH


class AssetResolver:
    """资产身份解析器。"""

    def __init__(self, catalog: Optional[List[Dict[str, Any]]] = None):
        self.catalog = catalog if catalog is not None else self._load_catalog()

    def _load_catalog(self) -> List[Dict[str, Any]]:
        path = Path(ASSET_CATALOG_PATH)
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return list(data.get("assets", []))
        except (json.JSONDecodeError, OSError):
            return []

    def resolve(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析工具调用的资产身份。

        Returns:
            {
                "matched": bool,
                "asset_id": str,
                "asset_type": str,
                "sensitivity": str,   # LOW / MEDIUM / HIGH / CRITICAL
                "owner": str,
                "policy": str,         # allow / require_review / require_approval / block
            }
        """
        params = params or {}
        text = self._collect_text(params)
        path = str(
            params.get("file_path")
            or params.get("path")
            or params.get("file")
            or ""
        )

        for asset in self.catalog:
            if self._match(asset, text, path):
                return {
                    "matched": True,
                    "asset_id": str(asset.get("id", "")),
                    "asset_type": str(asset.get("asset_type", "")),
                    "sensitivity": str(asset.get("sensitivity", "MEDIUM")),
                    "owner": str(asset.get("owner", "")),
                    "policy": str(asset.get("policy", "require_review")),
                }

        return {
            "matched": False,
            "asset_id": "",
            "asset_type": "",
            "sensitivity": "LOW",
            "owner": "",
            "policy": "allow",
        }

    def _match(self, asset: Dict[str, Any], text: str, path: str) -> bool:
        """按关键词与扩展名匹配资产。"""
        extensions = asset.get("extensions", [])
        if extensions and path:
            lower_path = path.lower()
            if not any(lower_path.endswith(ext.lower()) for ext in extensions):
                return False

        patterns = asset.get("patterns", [])
        return any(str(p).lower() in text.lower() for p in patterns)

    def _collect_text(self, params: Dict[str, Any]) -> str:
        """收集参数文本用于匹配。"""
        parts = []
        for value in params.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if isinstance(v, str))
        return " ".join(parts)


def create_asset_resolver() -> AssetResolver:
    """创建资产身份解析器。"""
    return AssetResolver()
