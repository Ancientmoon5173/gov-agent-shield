/**
 * GovAgent-Shield OpenClaw 插件 hooks。
 *
 * 组合模式说明：
 * OpenClaw 的 runModifyingHook 会自动顺序执行所有插件的
 * before_tool_call，并在某个插件返回 block=true 时短路。
 * 因此本插件只返回自己的决策，不覆盖其他插件 hook。
 */

import type {
  PluginHookAfterToolCallEvent,
  PluginHookBeforeToolCallEvent,
  PluginHookBeforeToolCallResult,
  PluginHookToolContext,
} from "openclaw/plugin-sdk/types";
import { ShieldHttpClient, type ShieldHttpClientOptions } from "./http_client.js";
import { buildToolRequest } from "./tool_request.js";
import type { ShieldDecision, ToolRequest } from "./types.js";

export interface GovAgentShieldHooksOptions extends ShieldHttpClientOptions {
  enabled?: boolean;
  httpClient?: {
    sendToolRequest(request: ToolRequest): Promise<ShieldDecision>;
  };
  log?: (message: string) => void;
  warn?: (message: string) => void;
}

export interface GovAgentShieldHooks {
  beforeToolCall(
    event: PluginHookBeforeToolCallEvent,
    ctx: PluginHookToolContext,
  ): Promise<PluginHookBeforeToolCallResult | undefined>;
  afterToolCall(
    event: PluginHookAfterToolCallEvent,
    ctx: PluginHookToolContext,
  ): Promise<void>;
}

export function createGovAgentShieldHooks(
  options: GovAgentShieldHooksOptions = {},
): GovAgentShieldHooks {
  const enabled = options.enabled !== false;
  const log = options.log ?? ((message: string) => console.log(message));
  const warn = options.warn ?? ((message: string) => console.warn(message));
  const client =
    options.httpClient ??
    new ShieldHttpClient({
      endpoint: options.endpoint,
      timeoutMs: options.timeoutMs,
      failClosed: options.failClosed,
      log,
      warn,
    });

  return {
    async beforeToolCall(event, ctx) {
      if (!enabled) {
        return undefined;
      }

      const request = buildToolRequest(event, ctx);
      log(`[GovAgentShield] 捕获 ToolCall: ${request.tool_name}`);

      let decision: ShieldDecision;
      try {
        decision = await client.sendToolRequest(request);
      } catch (error) {
        // 防御深度：即使注入的客户端本身抛异常，也按 fail-close 处理。
        warn(`[GovAgentShield] 安全检测异常，按阻断处理: ${String(error)}`);
        decision = {
          decision: "block",
          action: "block",
          blocked: true,
          reason: "安全服务调用异常，安全策略默认阻断",
          risk_score: 1.0,
          risk_level: "CRITICAL",
        };
      }

      const normalizedDecision =
        String(decision.decision ?? decision.action).toLowerCase();

      log(formatShieldLog(request, decision));

      if (
        normalizedDecision === "allow" ||
        normalizedDecision === "warn"
      ) {
        return undefined;
      }

      const actionLabel =
        normalizedDecision === "kill"
          ? "kill（终止任务）"
          : normalizedDecision === "review"
            ? "review（当前按阻断处理）"
            : normalizedDecision === "block"
              ? "block"
              : "unknown";

      return {
        block: true,
        blockReason:
          decision.reason ||
          `安全策略拦截: ${actionLabel}`,
      };
    },

    async afterToolCall(event, _ctx) {
      log(
        `[GovAgentShield] after_tool_call: ${event.toolName} ` +
          `durationMs=${event.durationMs ?? "n/a"} ` +
          `error=${event.error ? "yes" : "no"}`,
      );
    },
  };
}

function formatShieldLog(request: ToolRequest, decision: ShieldDecision): string {
  const lines = [
    "========== GovAgent Shield ==========",
    `[Agent] ${request.agent_id}`,
    `[ToolCall] tool: ${request.tool_name}`,
    `args: ${JSON.stringify(request.parameters)}`,
    `[Security] risk: ${decision.risk_score}`,
    `stage: ${decision.defense_stage ?? "risk_engine"}`,
    `decision: ${String(decision.action).toUpperCase()}`,
    `reason: ${decision.reason || decision.decision_reason || ""}`,
    "=====================================",
  ];
  return lines.join("\n");
}