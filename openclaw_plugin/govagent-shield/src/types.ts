/**
 * GovAgent-Shield OpenClaw 插件本地类型定义。
 *
 * ToolRequest 与 Python 端 src/runtime/tool_request.py 对齐；
 * ShieldAction / ShieldDecision 统一引用 decision.ts，避免重复定义。
 */

export interface ToolRequest {
  session_id: string;
  agent_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  context: Record<string, unknown>;
  task_context?: Record<string, unknown>;
  timestamp: string;
}

export type { ShieldAction, ShieldDecision } from "./decision.js";
