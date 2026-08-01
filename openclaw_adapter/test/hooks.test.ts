/**
 * GovAgent-Shield OpenClaw 适配层测试。
 *
 * 模拟 OpenClaw beforeToolCall / afterToolCall 上下文，
 * 验证 ToolRequest 构建、捕获、日志输出。
 */

import { buildToolRequest } from "../src/tool_request.js";
import { createGovAgentShieldHooks } from "../src/hooks.js";
import type { BeforeToolCallContext } from "../src/types.js";

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

async function main() {
  console.log("========================================");
  console.log("GovAgent-Shield OpenClaw 适配层测试");
  console.log("========================================\n");

  // Test 1: ToolRequest 构建
  const ctx = createSampleContext();
  const req = buildToolRequest(ctx, "session-001", "agent-001");
  assert(req.tool_name === "read_document", "tool_name 应为 read_document");
  assert(req.session_id === "session-001", "session_id 应为 session-001");
  assert(req.agent_id === "agent-001", "agent_id 应为 agent-001");
  assert(
    req.parameters.file_path === "policy_document.txt",
    "parameters.file_path 应为 policy_document.txt",
  );
  assert(req.timestamp.length > 0, "timestamp 不应为空");
  console.log("[PASS] ToolRequest 构建\n");
  console.log(JSON.stringify(req, null, 2));
  console.log("");

  // Test 2: beforeToolCall 捕获
  let captured: unknown;
  const hooks = createGovAgentShieldHooks({
    sessionId: "session-001",
    agentId: "agent-001",
    log: (msg, data) => {
      if (msg.includes("ToolRequest")) captured = data;
    },
  });
  const result = await hooks.beforeToolCall(ctx);
  assert(result === undefined, "Phase 1 不应阻断");
  assert(captured !== undefined, "应捕获到 ToolRequest");
  const capturedReq = captured as Record<string, unknown>;
  assert(capturedReq.tool_name === "read_document", "捕获的 tool_name 应正确");
  console.log("[PASS] beforeToolCall 捕获并输出 ToolRequest 日志\n");

  // Test 3: afterToolCall 记录
  const afterResult = await hooks.afterToolCall({
    assistantMessage: ctx.assistantMessage,
    toolCall: ctx.toolCall,
    args: ctx.args,
    result: {
      content: [{ type: "text", text: "文件内容摘要..." }],
      details: {},
    },
    isError: false,
    context: ctx.context,
  });
  assert(afterResult === undefined, "Phase 1 不应覆盖结果");
  console.log("[PASS] afterToolCall 记录执行结果\n");

  // Test 4: 参数截断保护
  const bigCtx: BeforeToolCallContext = {
    ...createSampleContext(),
    toolCall: {
      ...createSampleContext().toolCall,
      arguments: { data: "x".repeat(5000) },
    },
    args: { data: "x".repeat(5000) },
  };
  const bigReq = buildToolRequest(bigCtx);
  // parameters 保留完整参数（安全层需要）
  assert(
    bigReq.parameters.data === "x".repeat(5000),
    "parameters 应保留完整参数供安全检测",
  );
  // context.tool_arguments_raw 应被截断（日志安全）
  const raw = bigReq.context.tool_arguments_raw as { truncated?: boolean };
  assert(raw.truncated === true, "日志中的原始参数应被截断");
  console.log("[PASS] 参数截断保护（parameters 完整 / 日志截断）\n");

  console.log("========================================");
  console.log("全部测试通过");
  console.log("========================================");
}

main().catch((err) => {
  console.error("测试失败:", err);
  process.exit(1);
});
