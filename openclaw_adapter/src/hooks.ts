/**
 * GovAgent-Shield Hook 适配器（Phase 2 组合模式）。
 *
 * 基于 OpenClaw AgentLoopConfig.beforeToolCall / afterToolCall 机制。
 *
 * 组合模式：
 * 1. Shield 安全检测优先执行
 * 2. 如果 Shield 返回 block/kill/review → 阻断，不再执行原 hook
 * 3. 如果 allow → 再执行原 OpenClaw hook
 */

import { buildToolRequest } from "./tool_request.js";
import {
  ShieldHttpClient,
  type ShieldDecision,
} from "./http_client.js";
import type { ToolRequest } from "./types.js";
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
  /** HTTP 客户端（Phase 2 必填，用于调用 Python 安全服务） */
  httpClient?: ShieldHttpClientLike;
  /** 自定义日志函数（默认 console.log） */
  log?: (message: string, data?: unknown) => void;
}

/** HTTP 客户端最小接口（便于测试注入 mock） */
export interface ShieldHttpClientLike {
  sendToolRequest(
    request: ToolRequest,
    signal?: AbortSignal,
  ): Promise<ShieldDecision>;
}

export interface GovAgentShieldHooks {
  /**
   * OpenClaw beforeToolCall 钩子（组合模式）。
   *
   * @param ctx OpenClaw beforeToolCall 上下文
   * @param signal AbortSignal（可选）
   * @param next 原 OpenClaw hook（组合调用，可选）
   */
  beforeToolCall(
    ctx: BeforeToolCallContext,
    signal?: AbortSignal,
    next?: (
      ctx: BeforeToolCallContext,
      signal?: AbortSignal,
    ) => Promise<ShieldBeforeToolCallResult | undefined>,
  ): Promise<ShieldBeforeToolCallResult | undefined>;

  /**
   * OpenClaw afterToolCall 钩子（组合模式）。
   *
   * @param ctx OpenClaw afterToolCall 上下文
   * @param signal AbortSignal（可选）
   * @param next 原 OpenClaw hook（组合调用，可选）
   */
  afterToolCall(
    ctx: ShieldAfterToolCallContext,
    signal?: AbortSignal,
    next?: (
      ctx: ShieldAfterToolCallContext,
      signal?: AbortSignal,
    ) => Promise<ShieldAfterToolCallResult | undefined>,
  ): Promise<ShieldAfterToolCallResult | undefined>;
}

/**
 * 创建 GovAgent-Shield OpenClaw 适配器 hooks（组合模式）。
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

  const httpClient = options?.httpClient ?? new ShieldHttpClient();

  return {
    beforeToolCall: async (
      ctx: BeforeToolCallContext,
      signal?: AbortSignal,
      next?: (
        ctx: BeforeToolCallContext,
        signal?: AbortSignal,
      ) => Promise<ShieldBeforeToolCallResult | undefined>,
    ): Promise<ShieldBeforeToolCallResult | undefined> => {
      const request = buildToolRequest(
        ctx,
        options?.sessionId,
        options?.agentId,
      );

      log("捕获 ToolCall，已生成 ToolRequest", request);

      // 1. Shield 安全检测优先执行
      let decision: ShieldDecision;
      try {
        decision = await httpClient.sendToolRequest(request, signal);
      } catch (error) {
        // fail-close：sendToolRequest 自身抛异常时同样阻断
        log("安全服务调用异常，按阻断处理（fail-close）", error);
        decision = {
          decision: "block",
          action: "block",
          blocked: true,
          reason: "安全服务调用异常，安全策略默认阻断",
          risk_score: 1.0,
          risk_level: "CRITICAL",
        };
      }

      log("安全服务返回决策", decision);

      // 2. Shield 阻断 → 直接返回 block，不执行原 hook
      if (decision.decision !== "allow") {
        return {
          block: true,
          reason: decision.reason || "安全策略拦截",
        };
      }

      // 3. 放行 → 执行原 OpenClaw hook（组合模式）
      if (next) {
        return await next(ctx, signal);
      }

      return undefined;
    },

    afterToolCall: async (
      ctx: ShieldAfterToolCallContext,
      signal?: AbortSignal,
      next?: (
        ctx: ShieldAfterToolCallContext,
        signal?: AbortSignal,
      ) => Promise<ShieldAfterToolCallResult | undefined>,
    ): Promise<ShieldAfterToolCallResult | undefined> => {
      log("ToolCall 执行完成", {
        tool_name: ctx.toolCall.name,
        tool_call_id: ctx.toolCall.id,
        is_error: ctx.isError,
        result_summary: summarizeResult(ctx.result),
      });

      // Phase 2：OutputGuard 脱敏接入点（后续实现 HTTP check_output）
      // 当前仅记录，不覆盖结果

      // 组合模式：执行原 OpenClaw hook
      if (next) {
        return await next(ctx, signal);
      }

      return undefined;
    },
  };
}

/** 生成工具结果摘要（避免日志爆炸） */
function summarizeResult(result: { content: unknown[]; details: unknown }) {
  const textParts = (result.content ?? [])
    .filter(
      (c) =>
        typeof c === "object" &&
        (c as { type?: string }).type === "text",
    )
    .map((c) => {
      const text = (c as { text?: string }).text ?? "";
      return text.length > 120 ? text.slice(0, 120) + "..." : text;
    });
  return {
    content_count: (result.content ?? []).length,
    text_preview: textParts[0] ?? "",
  };
}
