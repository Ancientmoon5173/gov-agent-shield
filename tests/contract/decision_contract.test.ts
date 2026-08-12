/**
 * Decision Contract 契约测试。
 *
 * 覆盖 Python Policy Engine 的 5 种 action 经
 * HTTP Client → Hook 的完整链路：
 * - allow  → execute
 * - warn   → execute + audit
 * - review → approval required
 * - block  → blocked
 * - kill   → terminated
 *
 * 同时验证 fail-close：
 * - unknown action → block / invalid_decision_contract
 * - 网络异常       → block / transport_failure
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShieldHttpClient } from "../../openclaw_plugin/govagent-shield/src/http_client.js";
import { createGovAgentShieldHooks } from "../../openclaw_plugin/govagent-shield/src/hooks.js";

const ENDPOINT = "http://127.0.0.1:8000";

function pythonResponse(payload: Record<string, unknown>) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as unknown as Response;
}

function makeEvent(toolName = "read_document") {
  return {
    toolName,
    params: { file_path: "policy_document.txt" },
    toolCallId: "call-contract-001",
  } as never;
}

function makeCtx() {
  return {
    toolName: "read_document",
    agentId: "default_agent",
    sessionId: "contract-session-001",
    sessionKey: "main",
    runId: "run-contract-001",
    toolCallId: "call-contract-001",
    channelId: "cli",
  } as never;
}

function basePayload(action: string) {
  return {
    action,
    risk_score: 0.3,
    reason: `python decision: ${action}`,
    policy_id: `contract:${action}`,
    risk_level: "MEDIUM",
    defense_stage: "risk_engine",
    decision_reason: `python decision: ${action}`,
  };
}

describe("Decision Contract: Python → HTTP Client → Hook", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("allow → 放行（execute）", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse(basePayload("allow")),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    const decision = await client.sendToolRequest({
      session_id: "s",
      agent_id: "a",
      tool_name: "read_document",
      parameters: {},
      context: {},
      timestamp: new Date().toISOString(),
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(decision.action).toBe("allow");
    expect(decision.policy_id).toBe("contract:allow");
    expect(result).toBeUndefined();
  });

  it("allow + decoy_route → shadow execute（params 改写）", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse({
        ...basePayload("allow"),
        decoy_route: {
          enabled: true,
          original_target: "policy_document.txt",
          redirect_target: "/engine/decoy/internal/policy_document.txt",
          reason: "高风险会话访问敏感资产",
          policy_id: "decoy_route:internal_document",
          target_param: "file_path",
        },
      }),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(result?.block).toBeUndefined();
    expect(result?.params?.file_path).toBe(
      "/engine/decoy/internal/policy_document.txt",
    );
  });

  it("allow + inject_token → tool_result_persist 注入令牌", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse({
        ...basePayload("allow"),
        inject_token: {
          token: "DPT-contract-001",
          policy_id: "data_provenance:inject:sensitive",
        },
      }),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    await hooks.beforeToolCall(makeEvent(), makeCtx());
    const result = hooks.toolResultPersist(
      {
        toolName: "read_document",
        toolCallId: "call-contract-001",
        message: {
          role: "toolResult",
          toolCallId: "call-contract-001",
          toolName: "read_document",
          content: [{ type: "text", text: "内部资料" }],
          details: {},
          isError: false,
          timestamp: 1,
        },
        isSynthetic: false,
      } as never,
      {} as never,
    );

    const content = result?.message?.content as Array<{
      type: string;
      text?: string;
    }>;
    expect(
      content.some((block) => block.text?.includes("DPT-contract-001")),
    ).toBe(true);
  });

  it("warn → 放行（execute）并记录审计", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse(basePayload("warn")),
    );
    const audit = vi.fn();
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({
      httpClient: client,
      log: audit,
    });

    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(result).toBeUndefined();
    expect(audit).toHaveBeenCalledWith(
      expect.stringContaining(
        "audit warn: policy=contract:warn reason=python decision: warn",
      ),
    );
  });

  it("review → approval required", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse(basePayload("review")),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(result?.block).toBeUndefined();
    expect(result?.requireApproval).toBeDefined();
    expect(result?.requireApproval?.title).toBe("GovAgent-Shield 安全审批");
  });

  it("block → deny-only 审批（拒绝后阻断）", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse(basePayload("block")),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(result?.block).toBeUndefined();
    expect(result?.terminate).toBeUndefined();
    expect(result?.requireApproval?.severity).toBe("critical");
    expect(result?.requireApproval?.allowedDecisions).toEqual(["deny"]);
  });

  it("kill → deny-only 审批并终止任务", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse(basePayload("kill")),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });
    const hooks = createGovAgentShieldHooks({ httpClient: client });

    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());

    expect(result?.block).toBeUndefined();
    expect(result?.terminate).toBe(true);
    expect(result?.requireApproval?.severity).toBe("critical");
    expect(result?.requireApproval?.allowedDecisions).toEqual(["deny"]);
  });

  it("unknown action → fail-close block / invalid_decision_contract", async () => {
    vi.mocked(fetch).mockResolvedValue(
      pythonResponse({ ...basePayload("weird"), action: "weird" }),
    );
    const client = new ShieldHttpClient({ endpoint: ENDPOINT });

    const decision = await client.sendToolRequest({
      session_id: "s",
      agent_id: "a",
      tool_name: "read_document",
      parameters: {},
      context: {},
      timestamp: new Date().toISOString(),
    });

    expect(decision.action).toBe("block");
    expect(decision.policy_id).toBe("invalid_decision_contract");
    expect(decision.reason).toContain("Decision contract violation");
  });

  it("网络异常 → fail-close block / transport_failure", async () => {
    vi.mocked(fetch).mockRejectedValue(new Error("ECONNREFUSED"));
    const client = new ShieldHttpClient({
      endpoint: ENDPOINT,
      failClosed: true,
    });

    const decision = await client.sendToolRequest({
      session_id: "s",
      agent_id: "a",
      tool_name: "read_document",
      parameters: {},
      context: {},
      timestamp: new Date().toISOString(),
    });

    expect(decision.action).toBe("block");
    expect(decision.policy_id).toBe("transport_failure");
  });
});
