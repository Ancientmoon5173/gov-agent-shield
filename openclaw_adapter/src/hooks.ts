/**
 * GovAgent-Shield Hook 适配器。
 *
 * 基于 OpenClaw AgentLoopConfig.beforeToolCall / afterToolCall 机制。
 * Phase 1：仅捕获 ToolCall 并输出 ToolRequest 日志，不执行阻断。
 */

import { buildToolRequest } from "./tool_request.js";
import type {
  BeforeToolCallContext,
  ShieldAfterToolCallContext,
  ShieldAfterToolCallResult,
  ShieldBeforeToolCallResult,
} from "./types.js";

export interface ShieldHookOptions {
  /** 会话 ID（可从 harness 注入） */
  sessionId?: string;
  /** Agent ID（可从 harness 注入） */
  agentId?: string;
  /** 自定义日志函数（默认 console.log） */
  log?: (message: string, data?: unknown) => void;
}

export interface GovAgentShieldHooks {
  /**
   * OpenClaw beforeToolCall 钩子。
   * 捕获 ToolCall → 构建 ToolRequest → 输出日志。
   * Phase 1 不阻断，始终返回 undefined。
   */
  beforeToolCall(
    ctx: BeforeToolCallContext,
  ): Promise<ShieldBeforeToolCallResult | undefined>;

  /**
   * OpenClaw afterToolCall 钩子。
   * 记录工具执行结果摘要。
   */
  afterToolCall(
    ctx: ShieldAfterToolCallContext,
  ): Promise<ShieldAfterToolCallResult | undefined>;
}

/**
 * 创建 GovAgent-Shield OpenClaw 适配器 hooks。
 */
export function createGovAgentShieldHooks(
  options?: ShieldHookOptions,
): GovAgentShieldHooks {
  const log =
    options?.log ??
    ((message: string, data?: unknown) => {
      console.log(`[GovAgentShield] ${message}`);
      if (data !== undefined) {
        console.log(JSON.stringify(data, null, 2));
      }
    });

  return {
    beforeToolCall: async (
      ctx: BeforeToolCallContext,
    ): Promise<ShieldBeforeToolCallResult | undefined> => {
      const request = buildToolRequest(
        ctx,
        options?.sessionId,
        options?.agentId,
      );

      log("捕获 ToolCall，已生成 ToolRequest", request);

      // Phase 1：只记录，不阻断
      // Phase 2：调用 ShieldHttpClient → 根据决策返回 { block: true, reason }
      return undefined;
    },

    afterToolCall: async (
      ctx: ShieldAfterToolCallContext,
    ): Promise<ShieldAfterToolCallResult | undefined> => {
      log("ToolCall 执行完成", {
        tool_name: ctx.toolCall.name,
        tool_call_id: ctx.toolCall.id,
        is_error: ctx.isError,
        result_summary: summarizeResult(ctx.result),
      });

      // Phase 1：只记录，不覆盖结果
      // Phase 2：调用 OutputGuard → 返回脱敏后的 AfterToolCallResult
      return undefined;
    },
  };
}

/** 生成工具结果摘要（避免日志爆炸） */
function summarizeResult(result: { content: unknown[]; details: unknown }) {
  const textParts = (result.content ?? [])
    .filter((c) => typeof c === "object" && (c as { type?: string }).type === "text")
    .map((c) => {
      const text = (c as { text?: string }).text ?? "";
      return text.length > 120 ? text.slice(0, 120) + "..." : text;
    });
  return {
    content_count: (result.content ?? []).length,
    text_preview: textParts[0] ?? "",
  };
}
