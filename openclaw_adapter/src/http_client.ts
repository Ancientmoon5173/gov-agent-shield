/**
 * GovAgent-Shield HTTP 客户端（Phase 2）。
 *
 * 通过 REST API 调用 Python 端安全服务。
 * 安全策略：未知 action 默认阻断（fail-close），HTTP 异常默认阻断。
 */

import type { ToolRequest } from "./types.js";

/** 安全服务返回的安全决策 */
export interface ShieldDecision {
  decision: "allow" | "block" | "kill" | "review";
  action: string;
  blocked: boolean;
  reason: string;
  risk_score: number;
  risk_level: string;
  defense_stage?: string;
  decision_reason?: string;
}

export interface ShieldHttpClientOptions {
  /** GovAgent-Shield Python 服务地址 */
  endpoint?: string;
  /** 超时时间（毫秒） */
  timeoutMs?: number;
}

export class ShieldHttpClient {
  private endpoint: string;
  private timeoutMs: number;

  constructor(options?: ShieldHttpClientOptions) {
    this.endpoint = options?.endpoint ?? "http://127.0.0.1:8000";
    this.timeoutMs = options?.timeoutMs ?? 5000;
  }

  /**
   * 发送 ToolRequest 到安全服务，返回安全决策。
   *
   * POST /security/check_tool
   * 响应: { blocked, action, risk_score, risk_level, reason, defense_stage, decision_reason }
   *
   * 安全策略：
   * - 未知 action → 默认 block（fail-close）
   * - HTTP 异常/超时 → 默认 block（fail-close）
   */
  async sendToolRequest(
    request: ToolRequest,
    signal?: AbortSignal,
  ): Promise<ShieldDecision> {
    const url = `${this.endpoint}/security/check_tool`;

    console.log(
      `[GovAgentShield] 调用安全服务: POST ${url}`,
    );

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    // 组合外部 AbortSignal
    const onExternalAbort = () => controller.abort();
    signal?.addEventListener("abort", onExternalAbort);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(
          `安全服务响应异常: HTTP ${response.status}`,
        );
      }

      const data = (await response.json()) as Record<string, unknown>;

      return {
        decision: normalizeDecision(data.action as string),
        action: String(data.action ?? "unknown"),
        blocked: Boolean(data.blocked ?? false),
        reason: String(data.reason ?? data.decision_reason ?? ""),
        risk_score: Number(data.risk_score ?? 0),
        risk_level: String(data.risk_level ?? "LOW"),
        defense_stage: data.defense_stage as string | undefined,
        decision_reason: data.decision_reason as string | undefined,
      };
    } catch (error) {
      // 安全策略：fail-close
      console.error(
        "[GovAgentShield] 安全服务调用失败，按阻断处理:",
        error,
      );
      return {
        decision: "block",
        action: "block",
        blocked: true,
        reason: "安全服务不可用，安全策略默认阻断",
        risk_score: 1.0,
        risk_level: "CRITICAL",
      };
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onExternalAbort);
    }
  }
}

/**
 * 将 action 映射为 decision。
 * 未知 action → block（fail-close）。
 */
function normalizeDecision(
  action: string,
): "allow" | "block" | "kill" | "review" {
  if (action === "allow") return "allow";
  if (action === "block") return "block";
  if (action === "kill") return "kill";
  if (action === "review") return "review";
  // 未知 action → 默认阻断
  return "block";
}
