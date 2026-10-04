# 技能组合协议

## 协议定位

本文件定义 `codex-governance-skills` 内部的组合协议 `composition-v1`。它只规定能力之间如何发现、调用、交换有限证据、处理缺失和结束；它不取代任何技能的事实所有权、项目计划、连续性账本或用户授权。

技能有两种合法用法：

- **独立运行**：技能只使用自己的输入和 Codex 基础能力完成核心工作。缺少可选协作者时，输出 `Open` 缺口并继续能安全完成的部分。
- **组合运行**：技能把有限的结构化信封交给可选协作者；协作者返回证据或建议，不能直接夺取调用方的计划、账本、权限或领域事实。

没有技能可以把另一个技能列为必需运行时依赖。组合关系必须是可选的、有限的、可追踪的，并且允许降级回独立流程。

能力清单和权责矩阵见 [skill-capability-registry.json](skill-capability-registry.json)。每个技能的 `required_dependencies` 必须为空；`optional_collaborators` 只表示可借用的能力，不表示强制加载。

## 权责矩阵

| 事实或动作 | 唯一所有者 | 其他技能可以做什么 |
|---|---|---|
| 用户目标、授权、回滚和最终用户结果 | `human-centered-reasoning-guard` | 提供证据、建议和风险，不覆盖门禁 |
| 项目结构、计划文件和阶段导航 | `bootstrap-codex-project` | 读取计划、提出变更，不另建计划 |
| 跨会话检查点、需求快照和恢复账本 | `durable-context` | 提供恢复摘要，不直接写账本 |
| 当前会话的计划执行和开发切片 | `project-agent-orchestrator` | 调用短期助手，不拥有项目计划 |
| 只读多角度审议 | `deliberate-project` | 产出发现和争议，不自动形成决策 |
| 意图对齐 | `intent-alignment` | 产出对齐卡，不修改代码或计划 |
| 根因诊断 | `diagnose` | 产出竞争假设和检查，不自行修复 |
| 测试驱动和用户路径验证 | `tdd-loop` | 修改授权范围内代码和测试 |
| 边界、依赖、容量和回滚健康 | `architecture-health` | 产出结构发现，不直接重构 |
| 能力错配与候选能力比较 | `capability-director` | 产出只读候选，不安装或启用 |
| Windows、Git、进程和产物执行证据 | `execution-reliability` | 预检、验证和有限重试，不拥有授权或账本 |

其他技能必须尊重所有者的结论。建议、历史经验、测试通过和审议发现都不能自动升级为当前事实或授权。

## 组合信封 `composition-v1`

机器可读的字段合同在 [composition.schema.json](composition.schema.json)；无第三方运行时也可以用仓库内的 `scripts/validate-composition.py` 校验一个信封或一条有限调用链。校验器只检查消息边界，不执行技能、不写项目文件，也不把收据当成宿主已经完成副作用的证明。

技能之间只交换有限信封，不传完整提示词、聊天记录、私有源码、完整账本或凭据：

```json
{
  "schema_version": "composition-v1",
  "request_id": "turn-or-task-id",
  "parent_request_id": null,
  "source_skill": "diagnose",
  "target_skill": "tdd-loop",
  "scope": "current task scope",
  "claim_kind": "observed | inferred | proposed | verified",
  "intent_status": "DECIDED | ASSUMED | OPEN | CONFLICTED",
  "recovery_status": "FOUND | PARTIAL | NOT_FOUND | CONFLICTED | BLOCKED_UNCERTAINTY",
  "action_status": "READY | WARN | BLOCKED | PARTIAL",
  "review_status": "PASS | ISSUE | ABSTAIN | OPEN",
  "execution_status": "IN_PROGRESS | COMPLETED | FAILED | UNKNOWN",
  "authority_owner": "human-centered-reasoning-guard",
  "side_effect": "none | project_write | external_write",
  "evidence_refs": ["finding-or-test-id"],
  "next_action": "one smallest executable action or null",
  "degradation": "standalone | composed | partial | blocked",
  "budget": {"chars": 3000, "calls": 3, "depth": 2},
  "lifecycle": "created | routed | running | waiting | partial | blocked | resumed | completed | abandoned"
}
```

必填字段为 `schema_version`、`request_id`、`parent_request_id`、`source_skill`、`target_skill`、`scope`、`claim_kind`、四类状态、`authority_owner`、`side_effect`、`evidence_refs`、`next_action`、`degradation`、`budget` 和 `lifecycle`。没有证据的字段写 `Open` 或 `null`，不得从自然语言摘要补齐。独立运行时 `source_skill` 与 `target_skill` 相同，且 `degradation` 必须是 `standalone`。

状态按领域分开：

- `recovery_status` 只表示上下文或证据是否找回；
- `action_status` 只表示动作是否可以执行；
- `review_status` 只表示审议或检查结论；
- `execution_status` 只表示当前动作生命周期；
- `intent_status` 只表示用户意图是否清楚。

不同技能不得把这些字段合并成一个自定义状态，也不得把一个领域的 `PASS` 当作另一个领域的 `COMPLETED`。

## 路由和调用规则

1. 用户目标和当前技能边界决定是否调用协作者；不能仅因为协作者存在就加载它。
2. 调用方必须声明 `source_skill`、`target_skill`、`scope`、`authority_owner` 和预算。
3. 协作者只能返回信封中的证据、建议、缺口或下一动作；不能修改调用方的权威文件，除非它本身拥有该写入权且用户已授权。
4. 同一 `request_id` 不得重复处理同一阶段；`parent_request_id` 用于追踪组合链，禁止回指祖先形成循环。
5. 组合深度默认不超过 2；调用次数和字符预算耗尽时停止扩展，返回 `partial` 或 `blocked`。
6. 缺少协作者时回退到 `degradation=standalone`；缺失只有在改变结果时才报告为 `Open`。
7. Guard 的授权、回滚和完成门禁优先级最高；任何技能都不能用自己的信封覆盖 Guard 的 `BLOCKED`。
8. 用户最新明确指令优先于历史摘要、自动路由和技能默认值；冲突必须标为 `CONFLICTED`。

调用链的每个 `request_id` 只能出现一次；父节点必须先存在，不能自指或形成环。`completed` 生命周期必须配合 `execution_status=COMPLETED`，`action_status=BLOCKED` 不得被子调用升级为 `READY` 或 `COMPLETED`。协议校验失败时，调用方应回退到自己的 standalone 流程，或把缺口标为 `blocked`。

## 生命周期和降级

组合请求使用以下生命周期：

```text
created -> routed -> running -> waiting -> resumed -> completed
                             \-> partial -> completed
                             \-> blocked
                             \-> abandoned
```

- `waiting` 只表示等待一个已声明的可选能力或外部结果，不得无限等待。
- `partial` 表示已完成的部分仍可安全交付，未完成部分必须写入 `next_action`。
- `blocked` 表示继续会扩大不确定影响，必须保留证据并停止。
- `abandoned` 表示用户取消、目标切换或生命周期已结束；不得自动恢复成活动任务。

没有 `.agent-context`、宿主端点、外部回执或某个原子技能时，组合系统不得创建替代账本、后台服务或递归代理。它应使用当前技能的 standalone fallback，并把真正影响结果的缺口放进信封。

## 单独使用合同

每个技能的 `SKILL.md` 必须能够在没有其他集合技能的情况下说明：

- 触发条件和不触发条件；
- 自己拥有的输入、输出和写入边界；
- 缺少可选协作者时的 fallback；
- 失败、未知、冲突和恢复状态；
- 一个最小下一动作和预算。

单独使用时不得因为无法完成另一个技能的职责而阻塞自己的核心任务。需要其他技能才能完成的部分必须明确标为 `Open`、`partial` 或 `blocked`。

## 验证要求

仓库验证必须覆盖四层：

1. **单技能合同**：入口、边界、输出和 fallback 存在。
2. **信封合同**：字段、状态域、预算、生命周期和来源可解析。
3. **组合负例**：循环、越权写入、缺失权威、预算耗尽和状态混用会被拒绝或降级。
4. **组合正例**：至少验证一条 `intent-alignment -> diagnose -> tdd-loop`、一条 `durable-context -> project-agent-orchestrator` 和一条 `execution-reliability -> human-centered-reasoning-guard` 的有限信封链。

这些测试验证协议和边界，不声称宿主会自动调用技能，也不把收据存在当作外部副作用成功。
