/**
 * 将 OpenClaw 真实 before_tool_call 事件转换为 GovAgent-Shield ToolRequest。
 *
 * session_id / agent_id 直接取自 OpenClaw Runtime 注入的
 * PluginHookToolContext，不伪造运行时身份。
 */

import type {
  PluginHookBeforeToolCallEvent,
  PluginHookToolContext,
} from "openclaw/plugin-sdk/types";
import type { ToolRequest } from "./types.js";

export function buildToolRequest(
  event: PluginHookBeforeToolCallEvent,
  ctx: PluginHookToolContext,
): ToolRequest {
  return {
    session_id: ctx.sessionId ?? ctx.sessionKey ?? "unknown-session",
    agent_id: ctx.agentId ?? "openclaw-agent",
    tool_name: event.toolName,
    parameters: normalizeParams(event.params),
    context: {
      run_id: ctx.runId ?? event.runId,
      tool_call_id: ctx.toolCallId ?? event.toolCallId,
      channel_id: ctx.channelId,
      tool_kind: event.toolKind ?? ctx.toolKind,
      tool_input_kind: event.toolInputKind ?? ctx.toolInputKind,
      derived_paths: event.derivedPaths,
    },
    task_context: normalizeTaskContext(
      (ctx as { taskContext?: unknown }).taskContext,
    ),
    timestamp: new Date().toISOString(),
  };
}

function normalizeParams(params: unknown): Record<string, unknown> {
  if (params && typeof params === "object" && !Array.isArray(params)) {
    return params as Record<string, unknown>;
  }
  if (Array.isArray(params)) {
    return { values: params };
  }
  return {};
}

function normalizeTaskContext(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}
