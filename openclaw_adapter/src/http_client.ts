/**
 * GovAgent-Shield HTTP 客户端（Phase 2 预留）。
 *
 * Phase 1：仅输出日志，不发起实际 HTTP 调用。
 * Phase 2：调用 Python 端安全服务 REST API。
 */

import type { ToolRequest } from "./types.js";

export interface ShieldHttpClientOptions {
  /** GovAgent-Shield Python 服务地址 */
  endpoint?: string;
  /** 是否启用实际 HTTP 调用（Phase 2 设为 true） */
  enabled?: boolean;
}

export class ShieldHttpClient {
  private endpoint: string;
  private enabled: boolean;

  constructor(options?: ShieldHttpClientOptions) {
    this.endpoint = options?.endpoint ?? "http://127.0.0.1:8000";
    this.enabled = options?.enabled ?? false;
  }

  /**
   * 发送 ToolRequest 到安全服务进行安全检查。
   *
   * Phase 1：仅记录日志，返回默认放行。
   * Phase 2：POST /security/check_tool → 返回安全决策。
   */
  async sendToolRequest(request: ToolRequest): Promise<boolean> {
    if (!this.enabled) {
      console.log("[GovAgentShield] HTTP 调用未启用（Phase 1），默认放行");
      return true;
    }

    console.log("[GovAgentShield] 即将调用安全服务:", this.endpoint);
    console.log(JSON.stringify(request, null, 2));

    // Phase 2 实现：
    // const response = await fetch(`${this.endpoint}/security/check_tool`, {
    //   method: "POST",
    //   headers: { "Content-Type": "application/json" },
    //   body: JSON.stringify(request),
    // });
    // return response.ok;

    return true;
  }
}
