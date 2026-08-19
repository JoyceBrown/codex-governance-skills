# 组合协议

## 设计目标

四个治理 Skill 负责不同事实所有权：Bootstrap 管项目结构，Durable 管跨会话状态，Guard 管行动门禁，Deliberate 管显式只读审议。五个原子 Skill 只提供局部工作能力，不能成为新的计划、账本或权限中心。

## 统一字段

组合调用可以使用 `request_id`、`status`、`scope`、`intent_status`、`evidence_refs`、`next_action` 和 `budget`。涉及连续性的输出还可以带 `requirements_hash`、`checkpoint` 和 `snapshot_id`。字段值必须有来源；没有来源时标为 `Open`，不从自然语言摘要猜测。

## 权威和降级

- 当前项目事实以代码、测试和原始项目文件为准。
- 当前需求以 `requirements.md` 为准；活动计划的权责由 Bootstrap 识别。
- `.agent-context` 只由 Durable 的生命周期维护，不由原子 Skill 直接写入。
- Guard 的阻断不可被其他 Skill 覆盖；缺少授权、回滚或基线时停止在门禁。
- Deliberate 的发现保留不确定性，不自动变成决策。
- 原子 Skill 缺席时回退到主代理的普通能力，记录真实缺口，不递归启动代理或服务。

## 成本预算

普通任务优先 0 次历史搜索、0 次外部发现和 1 次验证；只有当前证据不足且缺失会影响结果时，才进行一次定向检查。`capability-director` 最多返回 3 个候选。预算耗尽时返回 `NOT_FOUND` 或 `BLOCKED_UNCERTAINTY`，不扩大范围。

