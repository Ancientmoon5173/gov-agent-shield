/**
 * GovAgent-Shield OpenClaw 适配层导出入口。
 *
 * DEPRECATED：请使用 openclaw_plugin/govagent-shield 原生插件。
 * 本适配器仅作兼容保留，action 判断以 Decision Contract 为准。
 */

export { createGovAgentShieldHooks } from "./hooks.js";
export { buildToolRequest } from "./tool_request.js";
export { ShieldHttpClient } from "./http_client.js";
export * from "./types.js";
