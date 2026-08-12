/**
 * GovAgent-Shield OpenClaw 插件入口。
 *
 * 通过 OpenClaw 原生 before_tool_call / after_tool_call 插件机制接入，
 * 不修改 agent-loop.ts、不替换 Agent、不改 LLM 调用流程。
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { createGovAgentShieldHooks } from "./src/hooks.js";

export default definePluginEntry({
  id: "govagent-shield",
  name: "GovAgent-Shield",
  description: "政企 Agent 工具调用安全防护 Runtime 层",
  register(api: OpenClawPluginApi) {
    const cfg = api.pluginConfig as Record<string, unknown> | undefined;
    const endpoint =
      typeof cfg?.endpoint === "string" && cfg.endpoint.length > 0
        ? cfg.endpoint
        : "http://127.0.0.1:8000";
    const timeoutMs = typeof cfg?.timeoutMs === "number" ? cfg.timeoutMs : 5000;
    const enabled = cfg?.enabled !== false;
    const failClosed = cfg?.failClosed !== false;

    const hooks = createGovAgentShieldHooks({
      endpoint,
      timeoutMs,
      enabled,
      failClosed,
      log: (message) => api.logger.info(message),
      warn: (message) => api.logger.warn(message),
    });

    api.on("before_tool_call", (event, ctx) => hooks.beforeToolCall(event, ctx));
    api.on("tool_result_persist", (event, ctx) =>
      hooks.toolResultPersist(event, ctx),
    );
    api.on("after_tool_call", (event, ctx) => hooks.afterToolCall(event, ctx));
  },
});
