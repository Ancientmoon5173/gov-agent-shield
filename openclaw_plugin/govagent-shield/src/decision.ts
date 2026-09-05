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
  decoy_route?: DecoyRoute;
  inject_token?: DataProvenanceInjectToken;
  /** V1 闭环：引擎审批 ID（review 时返回） */
  approval_id?: string;
  /** V1 闭环：决策初始执行状态（PENDING_EXECUTION / PENDING_APPROVAL / NOT_EXECUTED） */
  execution_status?: string;
  /** V1 闭环：一次工具调用的链路身份（供插件回写关联） */
  correlation?: {
    session_id?: string;
    chain_id?: string;
    call_id?: string;
    plugin_tool_call_id?: string;
  };
}

/**
 * Shadow Decoy 路由对象（方案 A）。
 *
 * 语义：安全策略驱动的执行目标重定向，而不是普通参数修改。
 * 由 Python Policy Engine 决策，Node Hook 只负责转换为
 * OpenClaw 可识别的 params 改写。
 */
export interface DecoyRoute {
  enabled: boolean;
  original_target: string;
  redirect_target: string;
  reason: string;
  policy_id: string;
  target_param?: string;
}

/**
 * 数据溯源令牌注入指令（方案 C-2b）。
 *
 * Python Policy Engine 对敏感读取决策返回该指令；
 * Hook 在 tool_result_persist 阶段把 token 追加进工具结果消息，
 * 使 Agent 上下文携带唯一数据溯源标记，外发时由引擎扫描拦截。
 */
export interface DataProvenanceInjectToken {
  token: string;
  policy_id: string;
  inject_mode?: string;
  target_param?: string;
}
