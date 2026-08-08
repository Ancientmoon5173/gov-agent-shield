/**
 * GovAgent-Shield 插件单元测试。
 *
 * 验证：
 * - 插件通过 api.on 注册 before_tool_call / after_tool_call
 * - allow/warn 放行、block 阻断、kill 终止、review 触发审批
 * - 未知 action 与 HTTP 异常 fail-close
 * - ToolRequest 携带真实 session_id / agent_id
 */

import { describe, expect, it, vi } from "vitest";
import { createGovAgentShieldHooks } from "../src/hooks.js";
import { normalizeAction } from "../src/http_client.js";
import { buildToolRequest } from "../src/tool_request.js";
import type { PluginHookBeforeToolCallEvent, PluginHookToolContext } from "openclaw/plugin-sdk/types";

function makeEvent(overrides: Partial<PluginHookBeforeToolCallEvent> = {}): PluginHookBeforeToolCallEvent {
  return {
    toolName: "read_document",
    params: { file_path: "policy_document.txt" },
    toolCallId: "call-001",
    ...overrides,
  };
}

function makeCtx(overrides: Partial<PluginHookToolContext> = {}): PluginHookToolContext {
  return {
    toolName: "read_document",
    agentId: "openclaw-agent-001",
    sessionId: "session-001",
    sessionKey: "main",
    runId: "run-001",
    toolCallId: "call-001",
    channelId: "cli",
    ...overrides,
  };
}

describe("buildToolRequest", () => {
  it("从真实 OpenClaw 上下文注入 session_id / agent_id", () => {
    const request = buildToolRequest(makeEvent(), makeCtx());
    expect(request.session_id).toBe("session-001");
    expect(request.agent_id).toBe("openclaw-agent-001");
    expect(request.tool_name).toBe("read_document");
    expect(request.parameters.file_path).toBe("policy_document.txt");
  });

  it("缺少显式 sessionId 时回退 sessionKey，仍不伪造身份", () => {
    const ctx = makeCtx({ sessionId: undefined });
    const request = buildToolRequest(makeEvent(), ctx);
    expect(request.session_id).toBe("main");
  });
});

describe("createGovAgentShieldHooks", () => {
  it("warn 时放行，不返回阻断结果", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "warn",
          reason: "低风险行为，已记录",
          risk_score: 0.3,
          risk_level: "MEDIUM",
          policy_id: "disposition:warn",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result).toBeUndefined();
  });

  it("allow 时放行，不返回阻断结果", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "allow",
          reason: "",
          risk_score: 0,
          risk_level: "LOW",
          policy_id: "disposition:allow",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result).toBeUndefined();
  });

  it("block 时返回 block=true", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "block",
          reason: "检测到诱饵敏感资源",
          risk_score: 0.85,
          risk_level: "CRITICAL",
          policy_id: "decoy:block",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result?.block).toBe(true);
    expect(result?.blockReason).toBe("检测到诱饵敏感资源");
  });

  it("kill 时按阻断处理", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "kill",
          reason: "行为链检测到数据外传",
          risk_score: 1,
          risk_level: "CRITICAL",
          policy_id: "disposition:kill",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result?.block).toBe(true);
    expect(result?.terminate).toBe(true);
  });

  it("review 触发 requireApproval 审批流程", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "review",
          reason: "需要人工审批",
          risk_score: 0.6,
          risk_level: "HIGH",
          policy_id: "permission:review",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result?.block).toBeUndefined();
    expect(result?.requireApproval).toBeDefined();
    expect(result?.requireApproval?.title).toBe("GovAgent-Shield 安全审批");
  });

  it("未知 action 默认阻断（fail-close）", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockResolvedValue({
          action: "weird-action",
          reason: "未知安全动作，按阻断处理",
          risk_score: 1,
          risk_level: "CRITICAL",
          policy_id: "invalid_decision_contract",
        }),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result?.block).toBe(true);
  });

  it("HTTP 异常时默认 fail-close", async () => {
    const hooks = createGovAgentShieldHooks({
      httpClient: {
        sendToolRequest: vi.fn().mockRejectedValue(new Error("connect ECONNREFUSED")),
      },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result?.block).toBe(true);
    expect(result?.blockReason).toContain("默认阻断");
  });

  it("enabled=false 时直接放行", async () => {
    const sendToolRequest = vi.fn();
    const hooks = createGovAgentShieldHooks({
      enabled: false,
      httpClient: { sendToolRequest },
    });
    const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
    expect(result).toBeUndefined();
    expect(sendToolRequest).not.toHaveBeenCalled();
  });
});

describe("normalizeAction", () => {
  it("支持 warn 且大小写兼容", () => {
    expect(normalizeAction("warn")).toBe("warn");
    expect(normalizeAction("WARN")).toBe("warn");
    expect(normalizeAction("Warn")).toBe("warn");
  });

  it("支持 allow / block / review / kill 且大小写兼容", () => {
    expect(normalizeAction("allow")).toBe("allow");
    expect(normalizeAction("ALLOW")).toBe("allow");
    expect(normalizeAction("block")).toBe("block");
    expect(normalizeAction("BLOCK")).toBe("block");
    expect(normalizeAction("review")).toBe("review");
    expect(normalizeAction("REVIEW")).toBe("review");
    expect(normalizeAction("kill")).toBe("kill");
    expect(normalizeAction("KILL")).toBe("kill");
  });

  it("未知值保持 fail-close 返回 block", () => {
    expect(normalizeAction("unknown-action")).toBe("block");
    expect(normalizeAction(undefined)).toBe("block");
    expect(normalizeAction("")).toBe("block");
  });
});
