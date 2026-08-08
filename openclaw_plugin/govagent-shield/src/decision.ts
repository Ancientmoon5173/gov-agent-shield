/**
 * GovAgent-Shield 统一安全决策契约。
 *
 * 全项目 action 的唯一定义来源：
 * - Python Policy Engine：唯一产生 action
 * - Node HTTP Client：只做传输、解析与 schema 校验
 * - Hook：只做 Decision Executor
 *
 * 禁止在 http_client.ts / hooks.ts / 其他 adapter 中自行定义 action 类型。
 */

export type ShieldAction =
  | "allow"
  | "warn"
  | "review"
  | "block"
  | "kill";

export interface ShieldDecision {
  action: ShieldAction;
  risk_score: number;
  reason: string;
  policy_id: string;
  risk_level?: string;
  defense_stage?: string;
  decision_reason?: string;
}
