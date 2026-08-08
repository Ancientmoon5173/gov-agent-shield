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
import type { ShieldAction, ShieldDecision } from "./decision.js";

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

  return {
    action,
    risk_score: Number(data.risk_score ?? 0),
    reason: String(data.reason ?? data.decision_reason ?? ""),
    policy_id: String(data.policy_id ?? "python_engine"),
    risk_level: String(data.risk_level ?? "LOW"),
    defense_stage: data.defense_stage as string | undefined,
    decision_reason: data.decision_reason as string | undefined,
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
