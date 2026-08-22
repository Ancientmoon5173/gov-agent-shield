"""
工具调用操作抽象。

将真实 OpenClaw 工具名与项目内演示工具名统一为业务操作，
供 BehaviorAnalyzer 进行基于 operation 的行为链分析。
"""

OPERATION_READ = "READ"
OPERATION_SEARCH = "SEARCH"
OPERATION_GENERATE = "GENERATE"
OPERATION_QUERY = "QUERY"
OPERATION_EXFIL = "EXFIL"
OPERATION_WRITE = "WRITE"
OPERATION_SYSTEM_EXEC = "SYSTEM_EXEC"
OPERATION_OTHER = "OTHER"


_TOOL_OPERATIONS = {
    "read": OPERATION_READ,
    "read_document": OPERATION_READ,
    "read_file": OPERATION_READ,
    "read_text": OPERATION_READ,
    "file_read": OPERATION_READ,
    "search": OPERATION_SEARCH,
    "search_knowledge_base": OPERATION_SEARCH,
    "search_files": OPERATION_SEARCH,
    "list_directory": OPERATION_SEARCH,
    "generate_summary": OPERATION_GENERATE,
    "generate_report": OPERATION_GENERATE,
    "report": OPERATION_GENERATE,
    "query_citizen_info": OPERATION_QUERY,
    "query": OPERATION_QUERY,
    "database_query": OPERATION_QUERY,
    "upload_file": OPERATION_EXFIL,
    "upload_data": OPERATION_EXFIL,
    "send_email": OPERATION_EXFIL,
    "http_request": OPERATION_EXFIL,
    "write_file": OPERATION_WRITE,
    "edit": OPERATION_WRITE,
    "apply_patch": OPERATION_WRITE,
    "exec": OPERATION_SYSTEM_EXEC,
    "bash": OPERATION_SYSTEM_EXEC,
}


def normalize_operation(tool_name: str) -> str:
    """将工具名归一化为行为分析使用的 operation。"""
    return _TOOL_OPERATIONS.get(str(tool_name), OPERATION_OTHER)
