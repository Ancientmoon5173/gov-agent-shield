/**
 * GovAgent-Shield OpenClaw 插件 hooks。
 *
 * 本文件只承担 Decision Executor 职责：
 * - allow  → undefined（放行）
 * - warn   → undefined（放行，记录审计日志）
 * - review → requireApproval(decision)（触发人工审批，可放行/拒绝）
 * - block  → deny-only 审批弹窗（仅可拒绝，保持阻断语义）
 * - kill   → deny-only 审批弹窗 + terminate（终止任务）
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
  PluginHookToolResultPersistContext,
  PluginHookToolResultPersistEvent,
  PluginHookToolResultPersistResult,
} from "openclaw/plugin-sdk/types";
import { ShieldHttpClient, type ShieldHttpClientOptions } from "./http_client.js";
import { buildToolRequest } from "./tool_request.js";
import type { DataProvenanceInjectToken } from "./decision.js";
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
  toolResultPersist(
    event: PluginHookToolResultPersistEvent,
    ctx: PluginHookToolResultPersistContext,
  ): PluginHookToolResultPersistResult | undefined;
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
  const pendingInjections = new Map<string, DataProvenanceInjectToken>();

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
      if (decision.inject_token) {
        const toolCallId = ctx.toolCallId ?? event.toolCallId ?? "";
        if (toolCallId) {
          pendingInjections.set(toolCallId, decision.inject_token);
        }
      }
      return executeDecision(decision, { log, warn });
    },

    toolResultPersist(event, _ctx) {
      const toolCallId = event.toolCallId ?? "";
      const injection = pendingInjections.get(toolCallId);
      if (!injection) {
        return undefined;
      }
      pendingInjections.delete(toolCallId);

      const message = event.message as {
        role?: string;
        content?: unknown;
      };
      if (message.role !== "toolResult") {
        return undefined;
      }

      const tokenLine = `\n[数据校验标记 ${injection.policy_id}: ${injection.token}]`;
      const content = Array.isArray(message.content)
        ? [...message.content]
        : [];
      if (typeof message.content === "string") {
        content.push({ type: "text", text: message.content });
      }
      content.push({ type: "text", text: tokenLine });

      log(
        `[GovAgentShield] data_provenance_injected: ` +
          `${injection.policy_id} token=${injection.token} toolCallId=${toolCallId}`,
      );
      return {
        message: {
          ...message,
          content,
        },
      } as PluginHookToolResultPersistResult;
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
      return applyDecoyRoute(decision, log);

    case "warn":
      // 放行，但记录审计日志
      log(
        `[GovAgentShield] audit warn: policy=${decision.policy_id} reason=${decision.reason}`,
      );
      return applyDecoyRoute(decision, log);

    case "review":
      return requireApproval(decision);

    case "block":
      return requireApproval(decision, { denyOnly: true });

    case "kill":
      return requireApproval(decision, {
        denyOnly: true,
        terminate: true,
      });

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
 * 将 Shadow Decoy 路由决策转换为 OpenClaw params 改写。
 *
 * 语义：安全策略驱动的执行目标重定向（shadow execute），
 * 不是普通参数修改。仅当 decoy_route.enabled 为 true 时生效。
 */
function applyDecoyRoute(
  decision: ShieldDecision,
  log: (message: string) => void,
): ShieldHookResult | undefined {
  const route = decision.decoy_route;
  if (!route?.enabled || !route.redirect_target) {
    return undefined;
  }

  log(
    `[GovAgentShield] decoy_route: ${route.original_target || "?"} -> ` +
      `${route.redirect_target} (policy=${route.policy_id})`,
  );

  const targetParam = route.target_param ?? "file_path";
  return {
    params: {
      [targetParam]: route.redirect_target,
    },
  };
}

/**
 * 安全决策的审批弹窗接口。
 *
 * review 与 block/kill 共用同一弹窗格式（标题、描述、超时），
 * 仅在 severity 与 allowedDecisions 上区分：
 * - review：warning，可 allow-once / allow-always / deny
 * - block/kill：critical，仅 deny（强制阻断，不可放行）
 */
export function requireApproval(
  decision: ShieldDecision,
  options: { denyOnly?: boolean; terminate?: boolean } = {},
): ShieldHookResult {
  const denyOnly = options.denyOnly ?? false;
  return {
    ...(options.terminate ? { terminate: true } : {}),
    requireApproval: {
      title: "GovAgent-Shield 安全审批",
      description: `${decision.reason || "该操作需要人工确认"}（policy: ${decision.policy_id}）`,
      severity: denyOnly ? "critical" : "warning",
      timeoutMs: 60_000,
      timeoutReason: "审批超时，按安全阻断处理",
      allowedDecisions: denyOnly
        ? ["deny"]
        : ["allow-once", "allow-always", "deny"],
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
