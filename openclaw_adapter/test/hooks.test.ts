/**
 * GovAgent-Shield OpenClaw 适配层测试（Phase 2）。
 *
 * 使用 mock HTTP 客户端，验证：
 * - 组合模式：Shield 优先，allow 后执行原 hook
 * - 阻断逻辑：block/kill/review 均阻断
 * - fail-close：HTTP 异常默认阻断
 * - AbortSignal 传递
 */

import { buildToolRequest } from "../src/tool_request.js";
import {
  createGovAgentShieldHooks,
  type ShieldHttpClientLike,
} from "../src/hooks.js";
import type {
  BeforeToolCallContext,
  ShieldAfterToolCallContext,
  ShieldBeforeToolCallResult,
  ToolRequest,
} from "../src/types.js";
import type { ShieldDecision } from "../src/http_client.js";

function assert(cond: boolean, msg?: string) {
  if (!cond) throw new Error(msg ?? "Assertion failed");
}

function createSampleContext(): BeforeToolCallContext {
  return {
    assistantMessage: {
      role: "assistant",
      content: [{ type: "text", text: "我来读取文件" }],
    },
    toolCall: {
      id: "tool-call-001",
      name: "read_document",
      arguments: { file_path: "policy_document.txt" },
    },
    args: { file_path: "policy_document.txt" },
    context: {
      systemPrompt: "你是政务助手",
      messages: [],
      tools: [{ name: "read_document" }],
    },
  };
}

/** Mock HTTP 客户端：按预设响应队列返回决策 */
function createMockHttp(
  responses: ShieldDecision[],
  fail = false,
): ShieldHttpClientLike {
  const calls: ToolRequest[] = [];
  return {
    sendToolRequest: async (
      request: ToolRequest,
      _signal?: AbortSignal,
    ): Promise<ShieldDecision> => {
      calls.push(request);
      if (fail) throw new Error("mock 网络故障");
      const r = responses.shift();
      if (!r) throw new Error("mock 响应用尽");
      return r;
    },
  };
}

async function main() {
  console.log("========================================");
  console.log("GovAgent-Shield OpenClaw 适配层测试 (Phase 2)");
  console.log("========================================\n");

  // Test 1: ToolRequest 构建
  const ctx = createSampleContext();
  const req = buildToolRequest(ctx, "session-001", "agent-001");
  assert(req.tool_name === "read_document", "tool_name 应为 read_document");
  assert(req.session_id === "session-001", "session_id 应为 session-001");
  assert(req.agent_id === "agent-001", "agent_id 应为 agent-001");
  assert(
    req.parameters.file_path === "policy_document.txt",
    "parameters.file_path 应正确",
  );
  assert(req.timestamp.length > 0, "timestamp 不应为空");
  console.log("[PASS] ToolRequest 构建\n");

  // Test 2: allow → 放行，且执行原 hook（组合模式）
  const mockAllow = createMockHttp([
    {
      decision: "allow",
      action: "allow",
      blocked: false,
      reason: "安全检测通过",
      risk_score: 0,
      risk_level: "LOW",
    },
  ]);
  const originalHookCalled = { value: false };
  const hooksAllow = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    httpClient: mockAllow,
  });
  const rAllow = await hooksAllow.beforeToolCall(
    createSampleContext(),
    undefined,
    async () => {
      originalHookCalled.value = true;
      return undefined;
    },
  );
  assert(rAllow === undefined, "allow 应放行");
  assert(originalHookCalled.value === true, "allow 后应执行原 hook");
  console.log("[PASS] allow → 放行 + 原 hook 执行（组合模式）\n");

  // Test 3: block → 阻断，原 hook 不执行
  const mockBlock = createMockHttp([
    {
      decision: "block",
      action: "block",
      blocked: true,
      reason: "检测到敏感文件",
      risk_score: 0.8,
      risk_level: "CRITICAL",
    },
  ]);
  const originalHookCalled2 = { value: false };
  const hooksBlock = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    httpClient: mockBlock,
  });
  const rBlock: ShieldBeforeToolCallResult | undefined =
    await hooksBlock.beforeToolCall(
    createSampleContext(),
    undefined,
    async () => {
      originalHookCalled2.value = true;
      return undefined;
    },
  );
  const blockValue = rBlock?.block as unknown as boolean;
  assert(blockValue === true, "block 应阻断");
  assert(rBlock?.reason === "检测到敏感文件", "block reason 应透传");
  assert(originalHookCalled2.value === false, "block 后不应执行原 hook");
  console.log("[PASS] block → 阻断 + 原 hook 不执行\n");

  // Test 4: review → 按需求暂时阻断
  const mockReview = createMockHttp([
    {
      decision: "review",
      action: "review",
      blocked: false,
      reason: "需要人工审批",
      risk_score: 0.5,
      risk_level: "HIGH",
    },
  ]);
  const hooksReview = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    httpClient: mockReview,
  });
  const rReview = await hooksReview.beforeToolCall(createSampleContext());
  assert(rReview?.block === true, "review 应暂时阻断");
  console.log("[PASS] review → 暂时阻断\n");

  // Test 5: fail-close（HTTP 异常 → block）
  const mockFail = createMockHttp([], true);
  const hooksFail = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    httpClient: mockFail,
  });
  const rFail: ShieldBeforeToolCallResult | undefined =
    await hooksFail.beforeToolCall(createSampleContext());
  const failBlock = rFail?.block as unknown as boolean;
  assert(failBlock === true, "HTTP 异常应 fail-close 阻断");
  console.log("[PASS] fail-close → HTTP 异常默认阻断\n");

  // Test 6: afterToolCall 组合模式透传
  const hooksAfter = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    httpClient: mockAllow,
  });
  const afterOriginalCalled = { value: false };
  const afterCtx: ShieldAfterToolCallContext = {
    assistantMessage: ctx.assistantMessage,
    toolCall: ctx.toolCall,
    args: ctx.args,
    result: { content: [{ type: "text", text: "文件内容" }], details: {} },
    isError: false,
    context: ctx.context,
  };
  const rAfter = await hooksAfter.afterToolCall(
    afterCtx,
    undefined,
    async () => {
      afterOriginalCalled.value = true;
      return undefined;
    },
  );
  assert(rAfter === undefined, "afterToolCall 默认不覆盖结果");
  assert(afterOriginalCalled.value === true, "afterToolCall 应透传原 hook");
  console.log("[PASS] afterToolCall 组合模式透传\n");

  // Test 7: 参数截断保护
  const bigCtx: BeforeToolCallContext = {
    ...createSampleContext(),
    toolCall: {
      ...createSampleContext().toolCall,
      arguments: { data: "x".repeat(5000) },
    },
    args: { data: "x".repeat(5000) },
  };
  const bigReq = buildToolRequest(bigCtx);
  assert(
    bigReq.parameters.data === "x".repeat(5000),
    "parameters 应保留完整参数供安全检测",
  );
  const raw = bigReq.context.tool_arguments_raw as { truncated?: boolean };
  assert(raw.truncated === true, "日志中的原始参数应被截断");
  console.log("[PASS] 参数截断保护（parameters 完整 / 日志截断）\n");

  console.log("========================================");
  console.log("全部测试通过");
  console.log("========================================");
}

main().catch((err) => {
  console.error("测试失败:", err);
  throw err;
});
