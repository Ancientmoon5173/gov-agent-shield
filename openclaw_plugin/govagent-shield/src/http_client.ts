/**
 * GovAgent-Shield HTTP 客户端。
 *
 * 安全策略：
 * - 未知 action 默认 block（fail-close）
 * - HTTP 异常/超时默认 block（fail-close）
 * - failClosed=false 时异常降级为 allow，并记录警告
 */

import type { ToolRequest, ShieldAction, ShieldDecision } from "./types.js";

export interface ShieldHttpClientOptions {
  endpoint?: string;
  timeoutMs?: number;
  failClosed?: boolean;
  log?: (message: string) => void;
  warn?: (message: string) => void;
}

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
      const action = normalizeAction(data.action);
      if (action === "block") {
        this.log(`[GovAgentShield] 未知安全动作，按阻断处理: ${String(data.action)}`);
      }
      return {
        decision: action,
        action: String(data.action ?? "unknown"),
        blocked: Boolean(data.blocked ?? false),
        reason: String(data.reason ?? data.decision_reason ?? ""),
        risk_score: Number(data.risk_score ?? 0),
        risk_level: String(data.risk_level ?? "LOW"),
        defense_stage: data.defense_stage as string | undefined,
        decision_reason: data.decision_reason as string | undefined,
      };
    } catch (error) {
      if (this.failClosed) {
        this.warn(`[GovAgentShield] 安全服务调用失败，按阻断处理: ${String(error)}`);
        return {
          decision: "block",
          action: "block",
          blocked: true,
          reason: "安全服务不可用，安全策略默认阻断",
          risk_score: 1.0,
          risk_level: "CRITICAL",
        };
      }
      this.warn(`[GovAgentShield] 安全服务不可用，failClosed=false 放行: ${String(error)}`);
      return {
        decision: "allow",
        action: "allow",
        blocked: false,
        reason: "安全服务不可用，但已配置 failClosed=false",
        risk_score: 0,
        risk_level: "LOW",
      };
    } finally {
      clearTimeout(timer);
    }
  }
}

function normalizeAction(action: unknown): ShieldAction {
  if (action === "allow") return "allow";
  if (action === "block") return "block";
  if (action === "kill") return "kill";
  if (action === "review") return "review";
  return "block";
}
