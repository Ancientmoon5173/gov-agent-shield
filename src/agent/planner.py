
"""
Agent Planner — 模拟 LLM 的规划能力。

输入：用户自然语言请求
输出：ToolCall（工具名 + 参数 + 推理理由）

不依赖任何外部 LLM API，通过意图识别生成工具调用。
"""

import re
from typing import Dict, Any, Callable, List, Tuple
from .models import ToolCall


class AgentPlanner:
    """
    Agent 规划器。模拟 LLM 的意图理解、工具选择和参数生成能力。
    
    通过关键词匹配识别用户意图，映射到对应工具，并生成合理参数。
    支持多种政企场景。
    """

    # 意图模式定义: (关键词列表, 工具名, 参数生成函数, 推理模板)
    INTENTS: List[Tuple[List[str], str, Callable, str]] = [
        # 场景1: 文档摘要
        (
            ["总结", "摘要", "概括", "归纳", "summarize", "简述"],
            "generate_summary",
            lambda u, kw: _extract_summary_params(u),
            "用户希望我对文档内容进行总结和摘要，适合使用 generate_summary 工具。"
        ),
        # 场景2: 知识搜索
        (
            ["搜索", "查找", "找一下", "搜一下", "search", "find", "知识库"],
            "search_knowledge_base",
            lambda u, kw: {"query": _extract_search_query(u)},
            "用户需要一个信息查询，适合使用 search_knowledge_base 工具从知识库中检索。"
        ),
        # 场景3: 读取文件（含诱饵触发）
        (
            ["财务", "预算", "审批", "预算审批", "财务预算"],
            "read_document",
            lambda u, kw: {"file_path": "data/decoys/" + _pick_decoy_file(u)},
            "用户请求访问财务相关文件，准备调用 read_document 读取指定文档。"
        ),
        # 场景4: 居民信息查询
        (
            ["查询", "查一下", "居民", "信息", "档案", "citizen", "身份证", "社保"],
            "query_citizen_info",
            lambda u, kw: _extract_citizen_params(u),
            "用户需要查询居民登记信息，适合使用 query_citizen_info 获取相关数据。"
        ),
        # 场景5: 上传/外传
        (
            ["上传", "发送", "外传", "发给", "email", "upload", "send", "传输", "备份"],
            "upload_data",
            lambda u, kw: _extract_upload_params(u),
            "用户请求将数据发送到外部，需要调用 upload_data 工具执行上传操作。"
        ),
        # 场景6: 文件读取（通用）
        (
            ["读取", "阅读", "打开", "查看文件", "read", "打开文件", "组织", "整理", "项目"],
            "read_document",
            lambda u, kw: {"file_path": _extract_file_path(u)},
            "用户需要读取或查看文件内容，使用 read_document 工具获取文档数据。"
        ),
    ]

    def plan(self, user_input: str) -> ToolCall:
        """
        规划一次工具调用。

        Args:
            user_input: 用户输入文本

        Returns:
            ToolCall: 包含工具名、参数和推理理由
        """
        matched_keywords = []

        for keywords, tool_name, param_fn, reasoning_template in self.INTENTS:
            for kw in keywords:
                if kw.lower() in user_input.lower():
                    matched_keywords.append(kw)

            if matched_keywords:
                # 找到匹配，生成参数和推理
                params = param_fn(user_input, matched_keywords)
                reasoning = reasoning_template

                return ToolCall(
                    tool_name=tool_name,
                    parameters=params,
                    reasoning=reasoning,
                )

        # 无匹配
        return ToolCall(
            tool_name="",
            parameters={},
            reasoning="无法从用户输入中识别出明确的工具调用意图。",
        )


# ========================
# 参数生成辅助函数
# ========================

def _extract_summary_params(user_input: str) -> Dict[str, Any]:
    """提取摘要工具的参数。"""
    # 查找文件名
    file_match = re.search(
        r'(政策文件|policy|文件|文档|方案|通知)(?:\.\w+)?',
        user_input
    )
    fname = (file_match.group(1) + ".txt") if file_match else "policy_document.txt"
    return {"content": f"请对 {fname} 进行摘要", "max_length": 200}


def _extract_search_query(user_input: str) -> str:
    """提取搜索查询词。"""
    # 去掉常见前缀
    query = user_input
    for prefix in ["搜索", "查找", "找一下", "搜一下", "search for", "find", "帮我"]:
        query = query.replace(prefix, "")
    # 去掉引号内的内容
    return query.strip()[:50] or "最新政策"


def _extract_citizen_params(user_input: str) -> Dict[str, Any]:
    """提取居民信息查询参数。"""
    known_names = ["张三", "李四", "王五", "赵六", "陈七"]
    for name in known_names:
        if name in user_input:
            return {"name": name, "id_number": ""}
    # 检查是否包含"全部"/"所有"
    if "全部" in user_input or "所有" in user_input or "all" in user_input.lower():
        return {"name": "全部", "id_number": ""}
    return {"name": "张三", "id_number": ""}


def _extract_upload_params(user_input: str) -> Dict[str, Any]:
    """提取上传工具的参数。"""
    data = "内部文件"
    target = "external"

    # 提取文件名
    file_keywords = ["工资", "员工", "内部", "文件", "资料", "信息"]
    for kw in file_keywords:
        if kw in user_input:
            data = f"{kw}数据"
            break

    # 提取目标
    if "邮箱" in user_input or "email" in user_input.lower():
        target = "external_email"
    elif "服务器" in user_input or "server" in user_input.lower():
        target = "external_server"
    elif "外部" in user_input:
        target = "external"

    return {"data": data, "target": target}


def _pick_decoy_file(user_input: str) -> str:
    """根据输入选择触发的诱饵文件。"""
    if "预算" in user_input or "审批" in user_input:
        return "财务预算审批表.xlsx"
    if "合同" in user_input:
        return "内部合同审批记录.docx"
    if "人事" in user_input or "档案" in user_input:
        return "人事信息汇总.pdf"
    return "财务预算审批表.xlsx"


def _extract_file_path(user_input: str) -> str:
    """提取文件路径。"""
    file_keywords = {
        "合同": "合同文件.docx",
        "政策": "policy_document.txt",
        "通知": "通知文件.txt",
        "方案": "实施方案.pdf",
        "项目": "project_materials.docx",
        "资料": "项目资料汇总.docx",
    }
    for kw, fname in file_keywords.items():
        if kw in user_input:
            return fname
    return "general_document.txt"


def create_planner() -> "AgentPlanner":
    """创建 Planner 实例。"""
    return AgentPlanner()
