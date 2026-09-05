/**
 * GovAgent-Shield HTTP 客户端。
 *
 * 职责边界：
 * 1. 发送 HTTP 请求
 * 2. 解析 JSON
 * 3. Decision Contract schema 校验
 *
 * 禁止在此判断 warn / review / kill 的策略含义。
 *
 * fail-close 策略：
 * - 网络异常且 failClosed=true → block / transport_failure
 * - 协议错误（unknown action）→ block / invalid_decision_contract
 */

import type { ToolRequest } from "./types.js";
import type {
  DataProvenanceInjectToken,
  DecoyRoute,
  ShieldAction,
  ShieldDecision,
} from "./decision.js";

export interface ShieldHttpClientOptions {
  endpoint?: string;
  timeoutMs?: number;
  failClosed?: boolean;
  log?: (message: string) => void;
  warn?: (message: string) => void;
}

const KNOWN_ACTIONS: readonly ShieldAction[] = [
  "allow",
  "warn",
  "block",
  "review",
  "kill",
];

export class ShieldHttpClient {
  private readonly endpoint: string;
  private readonly timeoutMs: number;
  private readonly failClosed: boolean;
  private readonly log: (message: string) => void;
  private readonly warn: (message: string) => void;

  constructor(options: ShieldHttpClientOptions = {}) {
    this.endpoint = options.endpoint ?? "http://127.0.0.1:8000";
    this.timeoutMs = options.timeoutMs ?? 5000;
    this.failClosed = options.failClosed !== false;
    this.log = options.log ?? ((message) => console.log(message));
    this.warn = options.warn ?? ((message) => console.warn(message));
  }

  /** 上报工具真实执行结果（after_tool_call）。best-effort，不 fail-close。 */
  async reportExecution(payload: {
    call_id: string;
    executed: boolean;
    error?: string;
    duration_ms?: number;
  }): Promise<{ ok: boolean }> {
    return this.postJson("/audit/execution", payload);
  }

  /** 上报审批结果（onResolution）。best-effort，不 fail-close。 */
  async resolveApproval(payload: {
    approval_id: string;
    action: "approve" | "deny";
    reviewer?: string;
    comment?: string;
  }): Promise<{ ok: boolean }> {
    return this.postJson(
      `/audit/approval/${encodeURIComponent(payload.approval_id)}`,
      {
        action: payload.action,
        reviewer: payload.reviewer ?? "openclaw-approval",
        comment: payload.comment ?? "",
      },
    );
  }

  private async postJson(
    path: string,
    body: unknown,
  ): Promise<{ ok: boolean }> {
    const url = `${this.endpoint}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        this.warn(
          `[GovAgentShield] audit POST ${path} 失败: HTTP ${response.status}`,
        );
        return { ok: false };
      }
      return { ok: true };
    } catch (error) {
      this.warn(
        `[GovAgentShield] audit POST ${path} 失败: ${String(error)}`,
      );
      return { ok: false };
    } finally {
      clearTimeout(timer);
    }
  }

  async sendToolRequest(request: ToolRequest): Promise<ShieldDecision> {
    const url = `${this.endpoint}/security/check_tool`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`安全服务响应异常: HTTP ${response.status}`);
      }

      const data = (await response.json()) as Record<string, unknown>;
      return parseDecision(data);
    } catch (error) {
      if (this.failClosed) {
        this.warn(
          `[GovAgentShield] 安全服务不可用，fail-close 阻断: ${String(error)}`,
        );
        return {
          action: "block",
          risk_score: 1.0,
          reason: "安全服务不可用，安全策略默认阻断",
          policy_id: "transport_failure",
          risk_level: "CRITICAL",
        };
      }
      this.warn(
        `[GovAgentShield] 安全服务不可用，failClosed=false 放行: ${String(error)}`,
      );
      return {
        action: "allow",
        risk_score: 0,
        reason: "安全服务不可用，但已配置 failClosed=false",
        policy_id: "transport_failure_degraded",
        risk_level: "LOW",
      };
    } finally {
      clearTimeout(timer);
    }
  }
}

/**
 * 解析并校验 Python Policy Engine 的响应。
 *
 * 仅做协议层归一化与 schema 校验，不解释任何策略语义。
 * unknown action 视为 Decision Contract violation，fail-close 为 block。
 */
export function parseDecision(data: Record<string, unknown>): ShieldDecision {
  const rawAction = data.action;
  const action = normalizeAction(rawAction);
  const decoyRoute = parseDecoyRoute(data.decoy_route);
  const injectToken = parseInjectToken(data.inject_token);

  if (action === "block" && !isKnownAction(rawAction)) {
    return {
      action: "block",
      risk_score: Number(data.risk_score ?? 1.0),
      reason: `Decision contract violation: unknown action '${String(rawAction)}'`,
      policy_id: "invalid_decision_contract",
      risk_level: "CRITICAL",
      defense_stage: String(data.defense_stage ?? ""),
    };
  }

  const correlation = parseCorrelation(data.correlation);
  return {
    action,
    risk_score: Number(data.risk_score ?? 0),
    reason: String(data.reason ?? data.decision_reason ?? ""),
    policy_id: String(data.policy_id ?? "python_engine"),
    risk_level: String(data.risk_level ?? "LOW"),
    defense_stage: data.defense_stage as string | undefined,
    decision_reason: data.decision_reason as string | undefined,
    ...(typeof data.approval_id === "string" && data.approval_id
      ? { approval_id: data.approval_id }
      : {}),
    ...(typeof data.execution_status === "string" && data.execution_status
      ? { execution_status: data.execution_status }
      : {}),
    ...(correlation ? { correlation } : {}),
    ...(decoyRoute ? { decoy_route: decoyRoute } : {}),
    ...(injectToken ? { inject_token: injectToken } : {}),
  };
}

/**
 * 解析并校验 V1 链路身份 correlation。
 * 结构不合法时返回 undefined，由 Hook 按普通决策执行。
 */
function parseCorrelation(
  raw: unknown,
): ShieldDecision["correlation"] | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  if (typeof record.call_id !== "string" || !record.call_id) {
    return undefined;
  }
  return {
    session_id:
      typeof record.session_id === "string" ? record.session_id : undefined,
    chain_id: typeof record.chain_id === "string" ? record.chain_id : undefined,
    call_id: record.call_id,
    plugin_tool_call_id:
      typeof record.plugin_tool_call_id === "string"
        ? record.plugin_tool_call_id
        : undefined,
  };
}

/**
 * 解析并校验 decoy_route 对象。
 *
 * 仅做协议层结构校验，不解释任何策略语义；
 * 结构不合法时丢弃该字段，由 Hook 按普通决策执行。
 */
function parseDecoyRoute(raw: unknown): DecoyRoute | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return undefined;
  }

  const record = raw as Record<string, unknown>;
  if (
    typeof record.enabled !== "boolean" ||
    typeof record.redirect_target !== "string" ||
    !record.redirect_target
  ) {
    return undefined;
  }

  return {
    enabled: record.enabled,
    original_target: String(record.original_target ?? ""),
    redirect_target: record.redirect_target,
    reason: String(record.reason ?? ""),
    policy_id: String(record.policy_id ?? ""),
    target_param:
      typeof record.target_param === "string" ? record.target_param : undefined,
  };
}

/**
 * 解析并校验 inject_token 注入指令。
 *
 * 仅做协议层结构校验，不解释任何策略语义；
 * 结构不合法时丢弃该字段，由 Hook 按普通决策执行。
 */
function parseInjectToken(raw: unknown): DataProvenanceInjectToken | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return undefined;
  }

  const record = raw as Record<string, unknown>;
  if (
    typeof record.token !== "string" ||
    !record.token ||
    typeof record.policy_id !== "string"
  ) {
    return undefined;
  }

  return {
    token: record.token,
    policy_id: record.policy_id,
    inject_mode:
      typeof record.inject_mode === "string"
        ? record.inject_mode
        : undefined,
    target_param:
      typeof record.target_param === "string"
        ? record.target_param
        : undefined,
  };
}

export function normalizeAction(action: unknown): ShieldAction {
  const normalized =
    typeof action === "string" ? action.trim().toLowerCase() : "";

  if (normalized === "allow") return "allow";
  if (normalized === "warn") return "warn";
  if (normalized === "block") return "block";
  if (normalized === "review") return "review";
  if (normalized === "kill") return "kill";

  return "block";
}

function isKnownAction(action: unknown): boolean {
  if (typeof action !== "string") {
    return false;
  }
  return (KNOWN_ACTIONS as readonly string[]).includes(
    action.trim().toLowerCase(),
  );
}
