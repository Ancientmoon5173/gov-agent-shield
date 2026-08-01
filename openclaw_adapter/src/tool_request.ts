/**
 * ToolRequest 构建器。
 *
 * 将 OpenClaw BeforeToolCallContext 转换为 GovAgent-Shield ToolRequest。
 */

import type { BeforeToolCallContext, ToolRequest } from "./types.js";

/**
 * 从 OpenClaw 上下文构建 ToolRequest。
 *
 * @param ctx OpenClaw beforeToolCall 上下文
 * @param sessionId 会话 ID（可从 harness 注入）
 * @param agentId Agent ID（可从 harness 注入）
 */
export function buildToolRequest(
  ctx: BeforeToolCallContext,
  sessionId?: string,
  agentId?: string,
): ToolRequest {
  return {
    session_id: sessionId ?? extractSessionId(ctx) ?? "unknown-session",
    agent_id: agentId ?? extractAgentId(ctx) ?? "unknown-agent",
    tool_name: ctx.toolCall.name,
    parameters: normalizeParams(ctx.args),
    context: {
      message_id: ctx.toolCall.id,
      assistant_message: sanitizeMessage(ctx.assistantMessage),
      tool_arguments_raw: sanitizeRaw(ctx.toolCall.arguments),
    },
    timestamp: new Date().toISOString(),
  };
}

/** 从上下文中尝试提取 session_id */
function extractSessionId(ctx: BeforeToolCallContext): string | undefined {
  const c = ctx.context as Record<string, unknown>;
  return typeof c?.sessionId === "string" ? c.sessionId : undefined;
}

/** 从上下文中尝试提取 agent_id */
function extractAgentId(ctx: BeforeToolCallContext): string | undefined {
  const c = ctx.context as Record<string, unknown>;
  return typeof c?.agentId === "string" ? c.agentId : undefined;
}

/** 规范化工具参数（确保是对象） */
function normalizeParams(args: unknown): Record<string, unknown> {
  if (args && typeof args === "object" && !Array.isArray(args)) {
    return args as Record<string, unknown>;
  }
  if (Array.isArray(args)) {
    return { values: args };
  }
  return {};
}

/** 清理 assistantMessage（截断过长内容） */
function sanitizeMessage(message: unknown): unknown {
  const json = sanitizeRaw(message);
  return json;
}

/** 清理原始参数（截断过长内容，防止日志爆炸） */
function sanitizeRaw(value: unknown): unknown {
  const str = JSON.stringify(value);
  if (!str) return value;
  const MAX = 2000;
  if (str.length <= MAX) return value;
  return { truncated: true, preview: str.slice(0, MAX) + "..." };
}
