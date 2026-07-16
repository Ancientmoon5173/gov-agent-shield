"""
动态诱捕与行为监控模块。

生成诱饵文件/目录/Token，监控 Agent 是否触碰了这些诱饵。
"""

from .decoy import DecoyGenerator
from .monitor import DecoyMonitor

__all__ = ["DecoyGenerator", "DecoyMonitor"]
