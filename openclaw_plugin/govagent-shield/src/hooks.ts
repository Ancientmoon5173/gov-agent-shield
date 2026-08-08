/**
 * GovAgent-Shield OpenClaw 插件 hooks。
 *
 * 本文件只承担 Decision Executor 职责：
 * - allow  → undefined（放行）
 * - warn   → undefined（放行，记录审计日志）
 * - review → requireApproval(decision)（触发人工审批）
 * - block  → { block: true, blockReason }
 * - kill   → { block: true, terminate: true, blockReason }
 * - unknown → fail-close block
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

/** OpenClaw 原生结果扩展：kill 附带 terminate 标记（由上层消费）。 */
export interface ShieldHookResult extends PluginHookBeforeToolCallResult {
  terminate?: boolean;
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
          action: "block",
          risk_score: 1.0,
          reason: "安全服务调用异常，安全策略默认阻断",
          policy_id: "transport_failure",
          risk_level: "CRITICAL",
        };
      }

      log(formatShieldLog(request, decision));
      return executeDecision(decision, { log, warn });
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

/**
 * Decision Executor：把统一决策转换为 OpenClaw Hook 结果。
 */
export function executeDecision(
  decision: ShieldDecision,
  context: {
    log?: (message: string) => void;
    warn?: (message: string) => void;
  } = {},
): ShieldHookResult | undefined {
  const log = context.log ?? ((message: string) => console.log(message));
  const warn = context.warn ?? ((message: string) => console.warn(message));

  switch (decision.action) {
    case "allow":
      return undefined;

    case "warn":
      // 放行，但记录审计日志
      log(
        `[GovAgentShield] audit warn: policy=${decision.policy_id} reason=${decision.reason}`,
      );
      return undefined;

    case "review":
      return requireApproval(decision);

    case "block":
      return {
        block: true,
        blockReason: decision.reason || "安全策略拦截",
      };

    case "kill":
      return {
        block: true,
        terminate: true,
        blockReason: decision.reason || "安全策略终止任务",
      };

    default:
      warn(
        `[GovAgentShield] Decision contract violation: ${String(decision.action)}`,
      );
      return {
        block: true,
        blockReason: "Decision contract violation",
      };
  }
}

/**
 * review 决策的审批接口。
 *
 * 当前映射到 OpenClaw 原生 requireApproval；
 * 后续可替换为独立的 ApprovalManager。
 */
export function requireApproval(
  decision: ShieldDecision,
): ShieldHookResult {
  return {
    requireApproval: {
      title: "GovAgent-Shield 安全审批",
      description: decision.reason || "该操作需要人工确认",
      severity: "warning",
      timeoutMs: 60_000,
      allowedDecisions: ["allow-once", "allow-always", "deny"],
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
    `policy: ${decision.policy_id}`,
    `stage: ${decision.defense_stage ?? "risk_engine"}`,
    `decision: ${decision.action.toUpperCase()}`,
    `reason: ${decision.reason || decision.decision_reason || ""}`,
    "=====================================",
  ];
  return lines.join("\n");
}
