# Framework-neutral coordination patterns

本参考把四个开源项目中有证据支持的协作机制转换成 `project-agent-orchestrator` 可以验证的协议字段。它不是这些项目的 API 兼容层，也不要求安装它们。

## Evidence snapshot

核对的公开源码和文档：

- [MetaGPT README](https://github.com/FoundationAgents/MetaGPT/blob/main/README.md) 将角色和软件公司的 SOP 作为协作骨架；[`team.py`](https://github.com/FoundationAgents/MetaGPT/blob/main/metagpt/team.py) 提供团队状态的 `serialize`/`deserialize`，[`role.py`](https://github.com/FoundationAgents/MetaGPT/blob/main/metagpt/roles/role.py) 保存角色状态并通过消息发布/接收推进动作。
- [ChatDev dynamic execution](https://github.com/OpenBMB/ChatDev/blob/main/docs/user_guide/en/dynamic_execution.md) 明确区分 edge-level 的 Map（扇出）和 Tree（扇出加归并），并要求 `max_parallel`；静态边的上下文会复制给每个动态实例。
- [CrewAI Flows](https://github.com/crewAIInc/crewAI/blob/main/docs/edge/en/concepts/flows.mdx) 提供可持久化的状态、监听器和 router；[Processes](https://github.com/crewAIInc/crewAI/blob/main/docs/edge/en/concepts/processes.mdx) 区分 sequential 与 hierarchical；条件任务根据前序结果选择性执行。
- [AutoGen termination conditions](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/conditions/_terminations.py) 将停止条件建模为可组合对象；[handoffs](https://github.com/microsoft/autogen/blob/main/python/docs/src/user-guide/core-user-guide/design-patterns/handoffs.ipynb) 使用事件和 topic subscription 把责任移交给另一个代理。

这些资料说明了机制存在，并不证明它们在所有版本或所有宿主中的运行语义相同。PAO 只吸收可映射到自己的身份、租约、任务、事件和恢复边界的部分。

## Absorbed mechanisms

### Role and SOP

MetaGPT 的角色和 SOP 被压缩为 `role_id`、`coordination_profile.pattern="sop"`、`sop_id` 和 `sop_step`。SOP 是任务契约的一部分，必须随计划/快照绑定并写入回调证据。角色状态只能通过持久化检查点恢复；聊天历史、模型自述和“我已经完成”不替代 `completed_claim` 或验收收据。

### Bounded fan-out and join

ChatDev 的 Map/Tree 语义被压缩为 `pattern="fan_out"`、`fanout_group_id`、`max_fanout`、`dependency_task_ids` 和 `join_policy`。`max_fanout` 表示同组的活动任务并发上限，终态任务释放额度；它不是累计任务总数。适配器在同一项目内执行这个上限；汇合仍由 `all`、`any` 或有明确阈值的 `bounded_partial` 决定。静态输入通过 `inputs_and_evidence_refs` 复制给每个任务，不能把隐藏聊天上下文当作共享状态。动态扩展必须重新走会话解析、能力预检和派发收据。

### State and conditional routing

CrewAI Flow 的状态、监听和 router 被压缩为项目快照、依赖屏障、`pattern="conditional"` 和不可变 `route_key`。路由选择由总指挥写入任务契约；后续代理只能执行已记录的分支，不能依据未持久化的临时文本自行改变计划。状态更新仍需检查计划代次和快照，失败或恢复从最新权威收据继续。

### Handoff and explicit termination

AutoGen 的 topic handoff 被压缩为 `pattern="handoff"`、`handoff_target_session_id`、直属父回调和 `wake_session`。移交目标必须是已解析并已认证的会话；移交不是验收，也不能绕过父代理。AutoGen 的可组合终止条件被压缩为必填的 `termination_conditions`，并与 `max_attempts`、租约截止、取消代次、依赖屏障和 `unknown` 封口共同决定停止。任何没有终态或取消路径的循环都拒绝派发。

## Deliberate exclusions

- 不引入框架的模型客户端、工具包、消息总线、向量记忆或常驻运行时。
- 不把角色名、聊天 topic、UI 状态或模型输出当作 canonical session identity。
- 不把框架内部的“任务返回”直接升级成 PAO 的 `accepted`；仍须由注册的验收权威发出唯一验收决策。
- 不把并行数量、router 标签或终止文本当作外部副作用授权；它们只是受验证的编排元数据。

## Mapping table

| 来源机制 | PAO 表达 | 强制边界 |
| --- | --- | --- |
| MetaGPT role/SOP | `role_id`, `sop_id`, `sop_step`, durable checkpoint | 角色租约、计划快照、父回调 |
| ChatDev map/tree | `fanout_group_id`, `max_fanout`, dependency barrier | 上限、每子任务收据、显式 join |
| CrewAI state/router | snapshot、`route_key`、dependency barrier | 路由持久化、计划代次、恢复 |
| AutoGen handoff/termination | `handoff_target_session_id`, wake receipt、`termination_conditions` | 目标认证、直属父、终态/取消封口 |
