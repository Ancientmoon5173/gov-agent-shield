"""
通用文件访问引用提取。

OpenClaw 真实接入中，Agent 可能通过 exec/bash 等执行类工具访问文件，
文件路径隐藏在 command 参数里。本模块对任意工具参数做统一提取：
- 专有路径字段：file_path / path / file / filename 等
- 命令字符串：cd 目标、引号内路径、盘符路径、带扩展名的文件引用

供 DecoyManager / AssetResolver 等模块共享，避免按工具名硬编码。
"""

import re
from typing import Any, Dict, List

_PATH_KEYS = (
    "file_path",
    "path",
    "file",
    "filename",
    "target_path",
    "source_path",
    "directory",
)

_COMMAND_KEYS = ("command", "cmdline", "script", "shell_command")

# 盘符绝对路径（如 E:\GovAgent-demo\a.txt）或带扩展名的相对引用
_PATH_TOKEN_RE = re.compile(
    r"(?P<path>[A-Za-z]:[\\/][^\s\"']+|"
    r"(?:\.[\\/])?[^\s\"';|&]+\.(?:xlsx|xls|docx|doc|pdf|csv|txt|json|md|sql|log|zip|py|ps1|sh|bat|xml|yaml|yml))",
    re.IGNORECASE,
)

_CD_RE = re.compile(r"(?:cd|cd /d)\s+[\"']?([^\"'\s;&|]+)")

_QUOTED_RE = re.compile(r"[\"']([^\"']+)[\"']")

_QUOTED_LOOKS_LIKE_PATH_RE = re.compile(r"[\\/]|\.\w+$")


def extract_file_references(params: Dict[str, Any]) -> List[str]:
    """
    从工具参数中提取可能的文件路径引用，去重保序。

    Args:
        params: ToolCall 参数

    Returns:
        候选路径/文件名列表
    """
    refs: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())

    for key in _PATH_KEYS:
        value = params.get(key)
        if isinstance(value, str):
            add(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                add(item)

    for key in _COMMAND_KEYS:
        command = params.get(key)
        if isinstance(command, str):
            refs.extend(_extract_paths_from_command(command))

    seen = set()
    result: List[str] = []
    for ref in refs:
        norm = ref.lower().rstrip("/\\")
        if norm not in seen:
            seen.add(norm)
            result.append(ref)
    return result


def _extract_paths_from_command(command: str) -> List[str]:
    """从命令字符串中提取路径与文件引用。"""
    refs: List[str] = []
    for match in _PATH_TOKEN_RE.finditer(command):
        refs.append(match.group("path"))
    for match in _CD_RE.finditer(command):
        refs.append(match.group(1))
    for match in _QUOTED_RE.finditer(command):
        quoted = match.group(1)
        if _QUOTED_LOOKS_LIKE_PATH_RE.search(quoted):
            refs.append(quoted)
    return refs
