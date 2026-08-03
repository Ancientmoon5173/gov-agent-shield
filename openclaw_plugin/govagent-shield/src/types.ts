/**
 * GovAgent-Shield OpenClaw 插件本地类型定义。
 *
 * ToolRequest 与 Python 端 src/runtime/tool_request.py 对齐。
 */

export interface ToolRequest {
  session_id: string;
  agent_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  context: Record<string, unknown>;
  timestamp: string;
}

export type ShieldAction = "allow" | "block" | "kill" | "review";

export interface ShieldDecision {
  decision: ShieldAction;
  action: string;
  blocked: boolean;
  reason: string;
  risk_score: number;
  risk_level: string;
  defense_stage?: string;
  decision_reason?: string;
}
