# 组合协议

## 设计目标

五个治理 Skill 负责不同事实所有权：Bootstrap 管项目结构，Durable 管跨会话状态，Guard 管行动门禁，Deliberate 管显式只读审议，Project Agent Orchestrator（PAO）管当前会话内的项目推进、恢复和可选内部辅助。六个原子 Skill 只提供局部工作能力，不能成为新的计划、账本或权限中心。

## 统一字段

组合调用可以使用 `request_id`、`status`、`scope`、`intent_status`、`evidence_refs`、`next_action` 和 `budget`。涉及连续性的输出还可以带 `requirements_hash`、`checkpoint` 和 `snapshot_id`。字段值必须有来源；没有来源时标为 `Open`，不从自然语言摘要猜测。

## 权威和降级

- 当前项目事实以代码、测试和原始项目文件为准。
- 当前需求以 `requirements.md` 为准；活动计划的权责由 Bootstrap 识别。
- `.agent-context` 只由 Durable 的生命周期维护，不由原子 Skill 直接写入。
- Guard 的阻断不可被其他 Skill 覆盖；缺少授权、回滚或基线时停止在门禁。
- Guard 内的 HCR 认知模块只消费授权投影、提出候选或验证请求，不新增权限层。WHY/WHAT 取当前用户要求和权威需求/计划；HOW 调整仍受原批准路线约束。认知状态与治理状态分开，Replay 分数和历史成功不能修改当前事实或完成状态。
- HCR 的需求列表和 ExperienceNode 是既有记录的只读投影，不建立第二需求账本或经验库。缺少目标、结果、进度或适用性证据时不得从旧摘要补齐；无可用历史就回到当前证据。跨 Skill 只交换既有信封与证据引用，不传整棵经验树。
- Deliberate 的发现保留不确定性，不自动变成决策。
- `project-agent-orchestrator` 负责当前会话内的项目计划执行、恢复和验证；它不拥有项目计划、领域验收、连续性账本或 Windows 执行状态。
- 原子 Skill 缺席时回退到主代理的普通能力，记录真实缺口，不递归启动代理或服务。
- `execution-reliability` 只负责执行证据和一次性重试判断；它不调用 `deliberate-project`，不修改治理文件，不写 `.agent-context`。它的 `review_candidate` 只是供显式审议入口参考的信号。

## 成本预算

普通任务优先 0 次历史搜索、0 次外部发现和 1 次验证；只有当前证据不足且缺失会影响结果时，才进行一次定向检查。`capability-director` 最多返回 3 个候选。预算耗尽时返回 `NOT_FOUND` 或 `BLOCKED_UNCERTAINTY`，不扩大范围。

## 项目执行示例

用户可以用自然语言描述项目级编排目标，例如：

```text
开启 PAO，按当前计划在本会话直接推进项目；需要时使用有界内部辅助，并在本会话完成验证和收据。
```

PAO 先核对项目根、唯一 active/exclusive 计划、当前任务和工作区，再在当前会话执行。内部辅助是可选的；没有宿主或辅助工具时仍可直接开发、验证和记录收据。references/ 和 scripts/ 中的历史兼容资料不属于启动条件或完成门禁。

