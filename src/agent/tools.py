"""
政企场景工具函数。

每个工具模拟一个真实的政府业务操作。
这些工具将在后续阶段被安全层包裹，实现调用检测和风险控制。
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain.agents import tool

# ========================
# 项目路径
# ========================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples" / "normal_tasks"


# ========================
# 工具1：读取政府文件
# ========================
@tool
def read_document(file_path: str) -> str:
    """
    读取一份政府内部文档的内容。

    用于查询政策文件、通知公告、工作报告等。
    只能访问 samples/normal_tasks 目录下的文件。

    Args:
        file_path: 文件名（如 "policy_document.txt"）

    Returns:
        文档内容文本
    """
    # 安全检查：限制只能读取指定目录
    allowed_dir = SAMPLES_DIR.resolve()
    target = (allowed_dir / file_path).resolve()

    # 防止路径穿越攻击（如 "../../etc/passwd"）
    if allowed_dir not in target.parents and target != allowed_dir:
        return f"错误：不允许访问 {file_path}，只能访问 {allowed_dir} 目录下的文件"

    if not target.exists():
        available = [f.name for f in allowed_dir.iterdir() if f.is_file()]
        return f"文件不存在。当前可访问的文件：{', '.join(available)}"

    content = target.read_text(encoding="utf-8")
    return content[:3000]  # 限制返回长度


# ========================
# 工具2：搜索内部知识库
# ========================
@tool
def search_knowledge_base(query: str) -> str:
    """
    在政务知识库中搜索相关信息。

    用于查询政策解读、办事指南、内部规章等。

    Args:
        query: 搜索关键词

    Returns:
        搜索结果列表
    """
    # 模拟知识库数据
    knowledge_base = {
        "数字化转型": {
            "title": "XX市数字化转型实施方案",
            "summary": "方案提出到2026年底，市级政务服务事项网上可办率达到95%以上，建成全市统一的数据共享交换平台。",
            "source": "policy_document.txt",
        },
        "一网通办": {
            "title": "深化一网通办改革要求",
            "summary": "整合各类政务服务系统，实现一次认证、全网通办。",
            "source": "政策文件库",
        },
        "网络安全": {
            "title": "网络安全保障措施",
            "summary": "建立网络安全态势感知平台，完善网络安全应急响应机制。",
            "source": "政策文件库",
        },
        "数据共享": {
            "title": "数据共享交换平台建设",
            "summary": "建设全市统一的政务云平台，实现基础设施共建共用、数据资源汇聚共享。",
            "source": "政策文件库",
        },
    }

    results = []
    for keyword, info in knowledge_base.items():
        if keyword in query or query in keyword:
            results.append(f"- {info['title']}: {info['summary']}")

    if not results:
        return f"未找到与 {query} 相关的知识条目"

    return "找到以下相关知识：\n" + "\n".join(results)


# ========================
# 工具3：查询居民信息
# ========================
@tool
def query_citizen_info(name: str, id_number: str = "") -> str:
    """
    查询指定居民的登记信息。

    注意：此操作涉及个人隐私，调用时会记录审计日志。
    根据《个人信息保护法》，仅限授权场景使用。

    Args:
        name: 居民姓名
        id_number: 身份证号（可选，提供后精确匹配）

    Returns:
        居民信息（已脱敏处理）
    """
    # 从模拟数据中查询
    citizen_file = SAMPLES_DIR / "citizen_data.txt"
    if not citizen_file.exists():
        return "居民信息数据库暂不可用"

    lines = citizen_file.read_text(encoding="utf-8").strip().split("\n")
    # 跳过说明行（从第3行开始是数据）
    data_lines = [l for l in lines if l and not l.startswith("说明") and not l.startswith("注意")]

    for line in data_lines[2:]:  # 跳过标题行和前两行说明
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        record_name = parts[0]
        record_id = parts[1]

        if record_name == name:
            if id_number and record_id != id_number:
                continue

            # 这里模拟脱敏处理（安全层的功能之一）
            masked_id = record_id[:6] + "********" + record_id[-4:]
            masked_phone = parts[3][:3] + "****" + parts[3][-4:] if len(parts[3]) >= 7 else parts[3]

            return (
                f"姓名：{record_name}\n"
                f"身份证号：{masked_id}\n"
                f"户籍地址：{parts[2]}\n"
                f"联系电话：{masked_phone}\n"
                f"社保状态：{parts[4]}\n"
                f"备注：{parts[5]}"
            )

    return f"未找到居民 {name} 的信息"


# ========================
# 工具4：生成文档摘要
# ========================
@tool
def generate_summary(content: str, max_length: int = 200) -> str:
    """
    对一段文本内容生成简洁的摘要。

    Args:
        content: 需要摘要的文本内容
        max_length: 摘要最大字数（默认200）

    Returns:
        摘要文本
    """
    if not content or len(content.strip()) < 20:
        return "内容太短，无需摘要"

    # 简单的抽取式摘要：取前几行中最有信息量的部分
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    important_lines = []

    for line in lines:
        # 跳过纯格式行
        if line.startswith("【") or line.startswith("#") or line.startswith("---"):
            continue
        # 跳过一、二、三等标题
        if line.startswith(("一", "二", "三", "四", "五", "（一", "（二", "（三")):
            important_lines.append(f"[要点] {line}")
            continue
        if len(line) > 15:
            important_lines.append(line)

    summary_text = "；".join(important_lines[:10])
    if len(summary_text) > max_length:
        summary_text = summary_text[:max_length] + "..."

    return f"内容摘要：\n{summary_text}" if summary_text else "无法生成摘要"


# ========================
# 工具注册
# ========================
GOV_TOOLS = [
    read_document,
    search_knowledge_base,
    query_citizen_info,
    generate_summary,
]

# 工具用途说明（用于安全策略和UI展示）
TOOL_METADATA = {
    "read_document": {
        "display_name": "读取文档",
        "risk_level": "MEDIUM",
        "description": "读取政府内部文档内容",
        "data_sensitivity": "内部文件",
    },
    "search_knowledge_base": {
        "display_name": "知识库搜索",
        "risk_level": "LOW",
        "description": "在政务知识库中搜索信息",
        "data_sensitivity": "公开信息",
    },
    "query_citizen_info": {
        "display_name": "居民信息查询",
        "risk_level": "HIGH",
        "description": "查询居民个人登记信息（需授权）",
        "data_sensitivity": "个人隐私",
    },
    "generate_summary": {
        "display_name": "生成摘要",
        "risk_level": "LOW",
        "description": "对内容生成简洁摘要",
        "data_sensitivity": "无",
    },
}