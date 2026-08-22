"""
secure_upload_file MCP stdio server。

仅用于 Demo：模拟安全上传工具，不真正外发数据。
真实外发前仍会经过 GovAgent-Shield before_tool_call。
"""

import json
import sys


TOOL_NAME = "secure_upload_file"


def send(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def initialize_result(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "secure-upload-file-mcp",
                "version": "1.0.0",
            },
        },
    }


def tools_list_result(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": (
                        "Simulated secure upload tool for GovAgent-Shield demo. "
                        "Does not send data externally."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "destination": {
                                "type": "string",
                                "enum": ["external", "internal"],
                            },
                        },
                        "required": ["file", "destination"],
                    },
                }
            ]
        },
    }


def tools_call_result(request_id, arguments):
    result = {
        "status": "simulated",
        "file": arguments.get("file", ""),
        "destination": arguments.get("destination", "external"),
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False),
                }
            ],
            "isError": False,
        },
    }


def error_result(request_id, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": message},
    }


def handle_request(request):
    method = request.get("method", "")
    request_id = request.get("id")

    if method == "initialize":
        return initialize_result(request_id)
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return tools_list_result(request_id)
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name", "")
        if name != TOOL_NAME:
            return error_result(request_id, f"Unknown tool: {name}")
        arguments = params.get("arguments", {}) or {}
        return tools_call_result(request_id, arguments)
    return error_result(request_id, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        response = handle_request(request)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
