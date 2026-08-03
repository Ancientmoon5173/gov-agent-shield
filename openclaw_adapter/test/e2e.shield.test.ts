/**
 * GovAgent-Shield OpenClaw 适配层 E2E 测试。
 *
 * 真实调用 Python FastAPI 安全服务：
 *   POST http://127.0.0.1:8000/security/check_tool
 *
 * 场景：
 *   1. 普通 read_document → allow
 *   2. 敏感文件读取 → block
 *   3. query_citizen_info + upload_data 行为链 → kill
 *
 * 前置条件：Python 安全服务已启动
 *   venv\Scripts\python -m uvicorn src.main:app --port 8000
 */

import { createGovAgentShieldHooks } from "../src/hooks.js";
import { ShieldHttpClient } from "../src/http_client.js";
import type { BeforeToolCallContext } from "../src/types.js";

// 如需覆盖默认地址，手动修改此处即可（避免依赖 @types/node）
const ENDPOINT = "http://127.0.0.1:8000";

function assert(cond: boolean, msg?: string) {
  if (!cond) throw new Error(msg ?? "Assertion failed");
}

/** 构造模拟 OpenClaw beforeToolCall 上下文 */
function makeCtx(
  toolName: string,
  args: Record<string, unknown>,
): BeforeToolCallContext {
  return {
    assistantMessage: {
      role: "assistant",
      content: [{ type: "text", text: `调用 ${toolName}` }],
    },
    toolCall: {
      id: `call-${toolName}-${Date.now()}`,
      name: toolName,
      arguments: args,
    },
    args,
    context: {
      systemPrompt: "你是政务助手",
      messages: [],
      tools: [],
    },
  };
}

async function waitForServer(): Promise<void> {
  const client = new ShieldHttpClient({ endpoint: ENDPOINT, timeoutMs: 1500 });
  try {
    await fetch(`${ENDPOINT}/health`);
  } catch {
    throw new Error(
      `Python 安全服务未启动（${ENDPOINT}）。请先运行: ` +
        `venv\\Scripts\\python -m uvicorn src.main:app --port 8000`,
    );
  }
}

async function main() {
  console.log("========================================");
  console.log("GovAgent-Shield × OpenClaw E2E 测试");
  console.log(`安全服务: ${ENDPOINT}`);
  console.log("========================================\n");

  await waitForServer();

  const hooks = createGovAgentShieldHooks({
    sessionId: "e2e-session-001",
    agentId: "default_agent",
    httpClient: new ShieldHttpClient({ endpoint: ENDPOINT }),
  });

  // ===== 场景 1: 普通 read_document → allow =====
  console.log("场景 1: 普通 read_document");
  const r1 = await hooks.beforeToolCall(
    makeCtx("read_document", { file_path: "policy_document.txt" }),
  );
  assert(r1 === undefined, `场景 1 应 allow（放行），实际: ${JSON.stringify(r1)}`);
  console.log("[PASS] 普通文件读取 → allow\n");

  // ===== 场景 2: 敏感文件读取 → block =====
  console.log("场景 2: 敏感文件读取 (secret_contract.pdf)");
  const r2 = await hooks.beforeToolCall(
    makeCtx("read_document", { file_path: "secret_contract.pdf" }),
  );
  assert(
    r2 !== undefined && r2.block === true,
    `场景 2 应 block（阻断），实际: ${JSON.stringify(r2)}`,
  );
  console.log(`[PASS] 敏感文件读取 → block (reason: ${r2?.reason})\n`);

  // ===== 场景 3: query_citizen_info + upload_data → kill =====
  console.log("场景 3: query_citizen_info → upload_data 行为链");
  const r3a = await hooks.beforeToolCall(
    makeCtx("query_citizen_info", { name: "张三" }),
  );
  console.log(`  第一步 query_citizen_info 决策: ${r3a?.block ? "block" : "放行"}`);

  const r3b = await hooks.beforeToolCall(
    makeCtx("upload_data", {
      data: "居民信息",
      target: "http://external",
    }),
  );
  assert(
    r3b !== undefined && r3b.block === true,
    `场景 3 第二步应 block/kill（行为链触发），实际: ${JSON.stringify(r3b)}`,
  );
  console.log(
    `[PASS] 行为链触发 → ${r3b?.block ? "block" : "未阻断"} (reason: ${r3b?.reason})`,
  );

  console.log("\n========================================");
  console.log("E2E 测试全部通过");
  console.log("========================================");
}

main().catch((err) => {
  console.error("E2E 测试失败:", err);
  throw err;
});
