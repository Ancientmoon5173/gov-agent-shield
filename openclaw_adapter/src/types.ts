/**
 * GovAgent-Shield OpenClaw 适配层类型定义。
 *
 * 与 Python 端 src/runtime/tool_request.py 的 ToolRequest 对齐。
 */

/** GovAgent-Shield ToolRequest 数据结构（与 Python 端一致） */
export interface ToolRequest {
  session_id: string;
  agent_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  context: Record<string, unknown>;
  timestamp: string;
}

/** OpenClaw ToolCall 块（来自 AssistantMessage.content） */
export interface OpenClawToolCall {
  id: string;
  name: string;
  arguments: unknown;
}

/** OpenClaw AgentLoopConfig.beforeToolCall 上下文 */
export interface BeforeToolCallContext {
  assistantMessage: unknown;
  toolCall: OpenClawToolCall;
  args: unknown;
  context: {
    systemPrompt: string;
    messages: unknown[];
    tools?: unknown[];
  };
}

/** OpenClaw beforeToolCall 返回值（Phase 2 阻断用） */
export interface ShieldBeforeToolCallResult {
  block?: boolean;
  reason?: string;
}

/** OpenClaw AgentLoopConfig.afterToolCall 上下文 */
export interface ShieldAfterToolCallContext {
  assistantMessage: unknown;
  toolCall: OpenClawToolCall;
  args: unknown;
  result: {
    content: unknown[];
    details: unknown;
  };
  isError: boolean;
  context: unknown;
}

/** OpenClaw afterToolCall 返回值（Phase 2 脱敏用） */
export interface ShieldAfterToolCallResult {
  content?: unknown[];
  details?: unknown;
  isError?: boolean;
  terminate?: boolean;
}
