# GovAgent-Shield开发规则

## 核心原则

这是一个Agent安全防护系统，不是普通文本匹配系统。

所有修改必须优先保证：
1. 不破坏安全检测逻辑
2. 不降低攻击样本覆盖能力
3. 不通过删除关键安全关键词绕过测试

## 修改原则

遇到测试失败：

禁止：
- 删除关键词解决冲突
- 降低检测范围
- 修改测试要求

优先：
- 调整意图优先级
- 增加上下文判断
- 增加风险权重
- 优化匹配策略


# Language Rule

所有解释、分析、修改计划必须使用中文。

代码中的：
- 类名
- 函数名
- 变量名

保持英文。

## Planner设计原则

高风险行为优先匹配：

upload_data
>
execute_command
>
query_sensitive_data
>
read_document
>
search
>
summary


## 每次修改后

必须：

pytest tests/

确认全部通过后才能提交。