/**
 * GovAgent-Shield OpenClaw 插件 hooks。
 *
 * 本文件只承担 Decision Executor 职责：
 * - allow  → undefined（放行）
 * - warn   → undefined（放行，记录审计日志）
 * - review → requireApproval(decision)（触发人工审批，可放行/拒绝）
 * - block  → deny-only 审批弹窗（仅确认，保持阻断语义）
 * - kill   → deny-only 审批弹窗 + terminate（仅确认，终止任务）
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
import type { ShieldAction, ShieldDecision, ToolRequest } from "./types.js";

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
      return executeDecision(decision, { log, warn, request });
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
    request?: ToolRequest;
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
      return requireApproval(decision, { request: context.request });

    case "block":
      return requireApproval(decision, {
        denyOnly: true,
        request: context.request,
      });

    case "kill":
      return requireApproval(decision, {
        denyOnly: true,
        terminate: true,
        request: context.request,
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
 * review 与 block/kill 共用同一弹窗格式（标题、描述、severity、按钮），
 * 仅在 severity 与 allowedDecisions 上区分：
 * - review：warning，允许一次 / 拒绝
 * - block：critical，仅确认（deny-only，强制阻断，不可放行）
 * - kill：critical，仅确认（deny-only）+ terminate
 *
 * OpenClaw 原生 severity 仅支持 info / warning / critical，
 * 因此按 review→warning、block/kill→critical 直接映射；
 * 若直接写入 review/block/kill 会被网关 schema 校验拒绝。
 * 插件不再声明 timeoutMs / timeoutReason，由网关使用原生默认时限。
 */
export function requireApproval(
  decision: ShieldDecision,
  options: {
    denyOnly?: boolean;
    terminate?: boolean;
    request?: ToolRequest;
  } = {},
): ShieldHookResult {
  const denyOnly = options.denyOnly ?? false;
  const prefix = APPROVAL_DESCRIPTION_PREFIX[decision.action] ?? "该操作需要人工审批";
  const reason = decision.reason || decision.decision_reason || "未提供原因";
  const operation = options.request
    ? formatRequestedOperation(options.request)
    : "";
  return {
    ...(options.terminate ? { terminate: true } : {}),
    requireApproval: {
      title: "GovAgent-Shield 安全审批",
      description: buildApprovalDescription(
        prefix,
        operation,
        reason,
        decision.policy_id,
      ),
      severity: denyOnly ? "critical" : "warning",
      allowedDecisions: denyOnly
        ? ["deny"]
        : ["allow-once", "deny"],
    },
  };
}

const APPROVAL_TOOL_LABELS: Record<string, string> = {
  read: "读取文件",
  read_document: "读取文件",
  list_directory: "列出目录",
  search_files: "搜索文件",
  exec: "执行命令",
  bash: "执行命令",
  write: "写入文件",
  write_file: "写入文件",
  edit: "编辑文件",
  apply_patch: "修改文件",
  upload_data: "上传数据",
  upload_file: "上传文件",
  send_email: "发送邮件",
  http_request: "发起网络请求",
  web_fetch: "获取网页内容",
  query_citizen_info: "查询居民信息",
};

const APPROVAL_PARAM_KEYS: Array<{ keys: string[] }> = [
  { keys: ["command", "cmdline", "script", "shell_command"] },
  { keys: ["file_path", "path", "file", "filename", "source_path", "target_path"] },
  { keys: ["target", "url", "uri"] },
  { keys: ["name", "id_number", "query"] },
  { keys: ["data", "content", "text"] },
];

function firstStringParam(
  params: Record<string, unknown>,
  keys: string[],
): string {
  for (const key of keys) {
    const value = params[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function formatRequestedOperation(request: ToolRequest): string {
  const toolName = request.tool_name;
  const label = APPROVAL_TOOL_LABELS[toolName] ?? toolName;
  const params = request.parameters ?? {};
  for (const group of APPROVAL_PARAM_KEYS) {
    const detail = firstStringParam(params, group.keys);
    if (detail) {
      return `${label}：${truncateApprovalText(detail, 200)}`;
    }
  }
  const raw = JSON.stringify(params);
  if (raw && raw.length > 2) {
    return `${label}：${truncateApprovalText(raw, 200)}`;
  }
  return label;
}

function truncateApprovalText(text: string, maxLength: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= maxLength) {
    return flat;
  }
  return `${flat.slice(0, maxLength - 1)}…`;
}

function buildApprovalDescription(
  prefix: string,
  operation: string,
  reason: string,
  policyId: string,
): string {
  const full = `${prefix}：${operation}。原因：${reason}（policy: ${policyId}）`;
  if (full.length <= 500) {
    return full;
  }
  const shortOperation = truncateApprovalText(operation, 120);
  const shortReason = truncateApprovalText(reason, 120);
  return `${prefix}：${shortOperation}。原因：${shortReason}（policy: ${policyId}）`;
}

const APPROVAL_DESCRIPTION_PREFIX: Record<string, string> = {
  review: "该操作需要人工审批",
  block: "安全策略已阻断该操作",
  kill: "安全策略已终止任务",
};

/** 日志字段区显示宽度（CJK 按双宽计算），中文翻译统一右对齐到该列。 */
const LOG_FIELD_DISPLAY_WIDTH = 40;

const ACTION_ZH_LABELS: Record<ShieldAction, string> = {
  allow: "放行",
  warn: "告警",
  review: "人工审批",
  block: "阻断",
  kill: "终止任务",
};

function isWideDisplayChar(ch: string): boolean {
  const code = ch.codePointAt(0) ?? 0;
  return (
    code >= 0x1100 &&
    (code <= 0x115f ||
      code === 0x2329 ||
      code === 0x232a ||
      (code >= 0x2e80 && code <= 0xa4cf && code !== 0x303f) ||
      (code >= 0xac00 && code <= 0xd7a3) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xfe10 && code <= 0xfe19) ||
      (code >= 0xfe30 && code <= 0xfe6f) ||
      (code >= 0xff00 && code <= 0xff60) ||
      (code >= 0xffe0 && code <= 0xffe6) ||
      (code >= 0x1f300 && code <= 0x1faff) ||
      (code >= 0x20000 && code <= 0x3fffd))
  );
}

function displayWidth(text: string): number {
  let width = 0;
  for (const ch of text) {
    width += isWideDisplayChar(ch) ? 2 : 1;
  }
  return width;
}

/** 左侧英文字段靠左，右侧中文翻译按显示宽度右对齐。 */
function alignedLogLine(left: string, right: string): string {
  const pad = Math.max(1, LOG_FIELD_DISPLAY_WIDTH - displayWidth(left));
  return `${left}${" ".repeat(pad)}（${right}）`;
}

function formatShieldLog(request: ToolRequest, decision: ShieldDecision): string {
  const action = decision.action;
  const actionZh = ACTION_ZH_LABELS[action] ?? action;
  const stage = decision.defense_stage ?? "risk_engine";
  const reason = decision.reason || decision.decision_reason || "";
  const argsJson = JSON.stringify(request.parameters);
  const lines = [
    "========== GovAgent Shield ==========",
    alignedLogLine(`[Agent] ${request.agent_id}`, `智能体 ID：${request.agent_id}`),
    alignedLogLine(`[ToolCall] tool: ${request.tool_name}`, `工具名称：${request.tool_name}`),
    alignedLogLine(`args: ${argsJson}`, `工具参数：${argsJson}`),
    alignedLogLine(`[Security] risk: ${decision.risk_score}`, `安全风险评分：${decision.risk_score}`),
    alignedLogLine(`policy: ${decision.policy_id}`, `策略 ID：${decision.policy_id}`),
    alignedLogLine(`stage: ${stage}`, `防御阶段：${stage}`),
    alignedLogLine(`decision: ${action.toUpperCase()}`, `决策动作：${actionZh}`),
    alignedLogLine(`reason: ${reason}`, `决策原因：${reason}`),
    "=====================================",
  ];
  return lines.join("\n");
}
