/**
 * GovAgent-Shield 输出预览工具。
 *
 * 不启动 OpenClaw 网关、不依赖 Python 服务，直接用 stub 决策驱动真实
 * beforeToolCall hook，打印五种决策（allow / warn / review / block / kill）
 * 的日志块与审批弹窗 JSON，用于快速迭代日志与弹窗格式。
 *
 * 普通测试运行（无 SHIELD_PREVIEW）只做断言，不打印；
 * 预览模式：
 *   powershell scripts\preview_plugin_output.ps1
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import { createGovAgentShieldHooks } from "../src/hooks.js";
import type {
  PluginHookBeforeToolCallEvent,
  PluginHookToolContext,
} from "openclaw/plugin-sdk/types";
import type { ShieldDecision } from "../src/types.js";

const previewEnabled = process.env.SHIELD_PREVIEW === "1";

function makeEvent(overrides: Partial<PluginHookBeforeToolCallEvent> = {}): PluginHookBeforeToolCallEvent {
  return {
    toolName: "read_document",
    params: { file_path: "/etc/passwd" },
    toolCallId: "call-preview-001",
    ...overrides,
  };
}

function makeCtx(overrides: Partial<PluginHookToolContext> = {}): PluginHookToolContext {
  return {
    toolName: "read_document",
    agentId: "001",
    sessionId: "session-preview",
    sessionKey: "main",
    runId: "run-preview",
    toolCallId: "call-preview-001",
    channelId: "cli",
    ...overrides,
  };
}

const SAMPLES: Array<{ label: string; decision: ShieldDecision }> = [
  {
    label: "ALLOW",
    decision: {
      action: "allow",
      risk_score: 0.1,
      reason: "安全检测通过",
      policy_id: "disposition:allow",
      risk_level: "LOW",
      defense_stage: "risk_engine",
    },
  },
  {
    label: "WARN",
    decision: {
      action: "warn",
      risk_score: 0.3,
      reason: "低风险行为，已记录",
      policy_id: "disposition:warn",
      risk_level: "MEDIUM",
      defense_stage: "risk_engine",
    },
  },
  {
    label: "REVIEW",
    decision: {
      action: "review",
      risk_score: 0.6,
      reason: "可疑行为，需要确认",
      policy_id: "permission:review",
      risk_level: "HIGH",
      defense_stage: "permission_checker",
    },
  },
  {
    label: "BLOCK",
    decision: {
      action: "block",
      risk_score: 0.85,
      reason: "检测到敏感文件访问",
      policy_id: "P001",
      risk_level: "CRITICAL",
      defense_stage: "risk_engine",
    },
  },
  {
    label: "KILL",
    decision: {
      action: "kill",
      risk_score: 1,
      reason: "行为链检测到数据外传",
      policy_id: "disposition:kill",
      risk_level: "CRITICAL",
      defense_stage: "behavior_analyzer",
    },
  },
];

async function runSample(sample: { label: string; decision: ShieldDecision }) {
  const logs: string[] = [];
  const hooks = createGovAgentShieldHooks({
    log: (message) => logs.push(message),
    httpClient: {
      sendToolRequest: async () => sample.decision,
    },
  });
  const result = await hooks.beforeToolCall(makeEvent(), makeCtx());
  const shieldLog = logs.find((line) => line.includes("========== GovAgent Shield"));
  return { shieldLog, result };
}

describe("GovAgent-Shield 输出预览", () => {
  it("五种决策均输出日志块，review/block/kill 附带审批弹窗", async () => {
    const outputs: string[] = [];
    for (const sample of SAMPLES) {
      const { shieldLog, result } = await runSample(sample);
      expect(shieldLog).toBeDefined();
      expect(shieldLog).toContain(`decision: ${sample.decision.action.toUpperCase()}`);
      expect(shieldLog).toContain("（决策动作：");

      if (sample.decision.action === "allow" || sample.decision.action === "warn") {
        expect(result).toBeUndefined();
      } else {
        expect(result?.requireApproval).toBeDefined();
        expect(result?.requireApproval?.description).toContain(sample.decision.policy_id);
        expect(result?.requireApproval?.timeoutMs).toBeUndefined();
      }

      if (previewEnabled) {
        outputs.push(`\n===== ${sample.label} =====\n${shieldLog}`);
        if (result?.requireApproval) {
          outputs.push(`----- ${sample.label} 弹窗 -----\n${JSON.stringify(result, null, 2)}`);
        }
      }
    }

    if (previewEnabled) {
      const previewText = outputs.join("\n") + "\n";
      const outputFile = process.env.SHIELD_PREVIEW_OUT;
      if (outputFile) {
        fs.writeFileSync(outputFile, previewText, "utf8");
      } else {
        console.log(previewText);
      }
    }
  });
});
