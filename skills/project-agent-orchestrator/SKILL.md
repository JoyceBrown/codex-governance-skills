---
name: project-agent-orchestrator
description: Coordinate a project commander with durable role-specific main sessions and bounded internal subagents after the user explicitly enables PAO mode; route tasks, authenticate and persist structured callbacks, and advance, wait, or block without polling loops. Do not use for an ordinary one-off subagent assignment or while PAO mode is disabled.
---

# Project Agent Orchestrator

将一个项目组织成一个总指挥主会话、零个或多个职责型长期主会话，以及每个主会话可创建的一次性或短期内部子代理。这里的“长期”指职责记录，不指某个永不更换的聊天线程：`role_id` 长期保留，`session_id` 可以在安全边界轮换。一次性任务使用 `ephemeral=true` 的临时线程，完成后关闭并归档，不进入默认桌面活动会话发现。这个 Skill 定义调度、身份、事件和回调协议；项目目标、计划权威、验收标准和外部操作授权仍由用户与项目权威文件决定。

本 Skill 只在目标类型所需的执行面真实可用时编排任务。内部子代理可以由父运行时本地创建、接收和持久化；职责型主会话和总指挥之间的跨会话编排必须具备宿主的会话创建/复用、任务发送、事件持久化、父会话唤醒和恢复接口。能力预检失败时返回 `capability_gap`，不得伪造 `task.dispatched` 或任务完成。

## PAO mode switch

PAO 默认关闭。只有用户明确发出以下任一指令，才允许后续任务使用本 Skill 的总指挥、职责会话、租约和回调编排：

- `开启 PAO 模式`
- `/pao on`

用户明确发出以下任一指令后，停止创建新的 PAO 会话、任务和派发收据，并按普通单会话或普通内部子代理流程处理后续任务：

- `关闭 PAO 模式`
- `/pao off`

关闭模式不会擅自终止已经派发的在途任务；在途任务必须完成、进入 `unknown`，或由用户明确要求取消后再收口。新对话或新的任务链默认重新从关闭状态开始，除非用户再次明确开启。每次任务的最终回复必须单独注明：`本次任务运行模式：PAO` 或 `本次任务运行模式：非 PAO`。

## Authority and hierarchy

- 每个项目只能有一个持有项目领导租约的项目总指挥主代理。`project_id`、`commander_session_id` 和 `commander_epoch` 必须在宿主权威状态中绑定；没有有效租约不得推进项目计划。
- 总指挥主代理可以创建自己的短期内部子代理，用于计划拆解、证据检查、任务包草拟和状态分析。
- 职责型主会话承担明确、可重复、需要独立上下文或生命周期的职责；它们也可以创建自己的短期内部子代理。
- 每个代理只有一个直属父代理。内部子代理只向直属父主代理返回结果；职责型主会话向总指挥回调。子代理不得改变项目计划权威、代表父代理宣布阶段完成，或绕过直属父代理直接推进计划。
- 不要把示例角色名（开发、架构、验收等）写死为系统角色；从当前项目计划和任务边界推导职责。

## Workflow

1. 核对项目根、当前计划、计划代次、当前快照、总指挥身份/领导租约和可用宿主适配器。发现多个可能的项目或计划时先解决身份冲突。
2. 将新任务压缩成目标、范围、非目标、验收、输出、权限、预算、依赖、快照和回调目标，并生成不可变的 `task_contract_hash`。
3. 按 [references/routing.md](references/routing.md) 判断任务应由总指挥自己处理、内部子代理处理，还是使用职责型主会话。
4. 对职责型主会话先执行会话解析：按项目、`role_id`、计划/快照、生命周期、租约、权限和健康状态列出候选。`reuse` 保留原会话和所有权；`takeover` 只变更**同一会话**的所有权；`new` 创建新会话。更换职责会话或总指挥会话属于接管/接续，须先按 [references/handoff-recovery.md](references/handoff-recovery.md) 完成旧会话核验、任务核对、停权和新身份生效，不得把 `takeover` 当作换会话。用户本次指令或已有项目规则已明确选择时直接执行；确有多个兼容候选且选择不明时才返回 `session_resolution_pending`。不得因会话未出现在侧栏就认定丢失，也不得静默创建同时活动的重复职责会话。
   如果用户明确要求“清理旧项目后重新开始”，且旧 commander/职责没有非终态任务，则走 `fresh_start`/`retire_and_recreate` 路径：先由宿主确认旧线程已关闭，再建立新基线和新会话；这条路径不发送 checkpoint，也不等待旧代理 ACK。只有要保留旧职责上下文或在途任务时才走 handoff。
5. 会话解析完成后，再按目标类型做能力预检。内部子代理要求父运行时能生成 canonical `target_session_id`、保留任务/事件收据并把结果交回父代理；职责型主会话和总指挥还要求宿主的跨会话创建/发送/持久化/唤醒/恢复接口。没有所需能力时返回 `target_unresolved` 或 `capability_gap`，不得使用显示名称、内部路径、会话列表图标或空闲状态猜测目标。
6. 由父运行时或适配器原子记录派发收据并发送任务包。参考适配器的 `dispatch()` 只验证并持久化状态；真实宿主必须使用带 `send_task` 预检和宿主回执的 `dispatch_to_host()`。发送结果不确定时记录 `task.unknown`；没有明确收据不得报告已派发。内部子代理的本地收据必须能在父会话恢复时重放。
7. 接收结构化事件。适配器先认证来源、校验项目/计划/快照/任务/尝试/父子身份和事件状态机，再去重、排序并持久化；事件必须标明 `receipt_origin`，`host_observed` 还必须带 `observed_by`。持久化成功后才唤醒直属父代理。协议见 [references/callback-protocol.md](references/callback-protocol.md)。
8. 对内部子代理，由直属主代理整合结果并发出正式汇总；对职责型主会话，由该主会话向总指挥回调。开发代理只能发出 `completed_claim` 和执行结果；自检不等于门禁验收。只有任务包指定的 `acceptance_authority_session_id` 可以发出 `accepted`/`rejected`，总指挥据此推进计划。
9. 总指挥验证回调、计划代次、快照和验收证据，然后只做一个有依据的选择：派发下一项、等待依赖、报告阻塞、取消、重新派发新尝试，或完成当前计划边界。并行任务只有在其依赖屏障满足后才能推进。
10. 在派发、尝试终态、父验收、阻塞、取消、恢复、领导租约、目标身份变化或临时会话清理时记录检查点。临时会话只有在宿主返回 `archived`/`closed` 收据后才算清理完成；没有归档/删除接口时报告 `capability_gap`，不要声称已删除。不要设置没有终态或取消条件的持续目标，也不要用轮询保持循环活跃。

职责归属于项目和角色，不归属于某个永久固定的会话 ID。计划性交接、会话失联、宿主重装、权限或上下文迁移都使用同一接续协议；旧会话能够回话时收取交接确认，不能回话时使用宿主核验和租约停权。每个任务或阶段边界、压缩完成后都评估是否应轮换该职责会话：提前关注上下文余量和成本；第一次压缩或上下文约 80% 时准备检查点，第二次压缩、上下文溢出或经核实的指令/计划漂移应停止继续派新任务并在安全边界轮换。`rotation_recommendation()` 提供纯函数门禁；没有可靠指标时不伪造百分比。压缩次数本身不证明代理失效；在有副作用的工作中先核对状态，再安全切换。已验收任务保留原收据；进行中且结果不明的尝试进入 `unknown` 并先核对副作用，不能把新会话接在旧 attempt 上。新会话获得新的规范 ID、租约和代次后才可派发；旧会话的迟到回调只能作为过期证据。轮换时必须按“创建持久 successor → prepare → checkpoint ack → commit → 归档旧宿主线程”顺序执行；commit 成功不等于旧线程已归档，清理失败必须单独报告。轮换时机与完整协议见 [references/handoff-recovery.md](references/handoff-recovery.md)。

## Routing rule

任务生命周期、结果所有权、独立上下文、验收责任、回调责任、恢复需要和副作用边界优先于任务复杂度。复杂度只能作为次要信号。低风险、短期、同一权限和同一上下文内的工作默认使用内部子代理；长期、有独立职责、需要复用或跨会话恢复的工作创建职责型主会话。详细判定表见 [references/routing.md](references/routing.md)。

## Coordination profiles

任务包可以携带一个框架无关的 `coordination_profile`，把执行图和停止条件写成可持久化、可复核的数据。它吸收了 MetaGPT 的角色/SOP、ChatDev 的有界扇出与汇合、CrewAI 的状态化条件路由，以及 AutoGen 的事件移交和显式终止语义，但不引入这些框架的运行时或消息总线。参考 [references/coordination-patterns.md](references/coordination-patterns.md)。

- `sequential`：按父任务和依赖屏障顺序推进。
- `sop`：用 `sop_id` 和 `sop_step` 绑定职责型角色的可恢复操作步骤；步骤完成仍须发出回调和验收收据。
- `fan_out`：用 `fanout_group_id` 和 `max_fanout` 表示活动任务的有界并行扩展；终态任务释放额度。子任务仍必须各自拥有任务契约，汇合使用 `dependency_task_ids` 与 `join_policy`。
- `conditional`：用不可变的 `route_key` 记录父代理已经作出的分支选择；路由结果不能只存在于聊天文本中。
- `handoff`：用 `handoff_target_session_id` 表示显式移交目标；移交只改变后续责任，不跳过父子链、权限校验或验收门禁。

每个 profile 都必须声明 `termination_conditions`。`max_attempts`、租约期限、取消代次和 `unknown` 封口共同构成停止条件；没有终止条件的循环不得派发。`fan_out` 的数量限制由适配器执行，profile 本身不创建会话，也不授予额外权限。

## Task contract

每次正式派发都要携带不可变、可复核的任务包，至少包含：

```text
schema_version
project_id
plan_id
plan_revision
snapshot_id
snapshot_hash
capability_check_id
permission_boundary
session_resolution: reuse | takeover | new
candidate_session_ids
role_epoch
previous_owner_session_id
handoff_receipt_id
acceptance_mode: commander_gate | independent_validator
acceptance_authority_session_id
acceptance_authority_permission_boundary
acceptance_scope_id
task_id
attempt_id
root_session_id
parent_session_id
target_kind: commander | main_session | internal_child
target_session_id
role_id (required for main_session, otherwise empty)
ancestor_session_ids
dispatch_depth
dependency_task_ids
join_policy
objective
allowed_scope
excluded_scope
acceptance_criteria
acceptance_policy_version
inputs_and_evidence_refs
output_contract
side_effects_policy
lease_id
commander_lease_id
lease_expires_at
cancel_epoch
max_attempts
budget_and_deadline
coordination_profile
callback_to
task_contract_hash
idempotency_key
```

`target_session_id` 对三种目标都必须存在；`parent_session_id` 只有项目总指挥根任务可以为空；`callback_to` 必须等于直属父会话。`ancestor_session_ids` 表示直属父会话之前的祖先，不包含 `parent_session_id` 本身；该字段、`dispatch_depth`、`root_session_id` 由适配器生成并校验，调用方不能自行缩短或改写。`dependency_task_ids` 与 `join_policy` 用于并行任务的屏障；没有依赖时明确使用空集合和 `all`/`none` 之一。需要部分汇合时使用 `{"mode":"bounded_partial","min_accepted":N}`，不能只写没有阈值的 `bounded_partial`。

任务包中的计划和快照字段必须与验收时的权威计划一致。计划或快照发生变化时，旧任务只能标为 `stale` 或创建新 `attempt_id`，不得静默套用新计划。重试保留逻辑 `task_id`，但必须使用新的 `attempt_id`、租约和幂等作用域；旧 attempt 的回调只能进入 `stale`。

`idempotency_key` 在一个适配器存储中必须全局唯一，推荐使用 `project_id/task_id/attempt_id/...` 前缀。适配器会拒绝同一幂等键跨任务或跨 attempt 重用；同一任务和 attempt 的重放才会返回 `duplicate`。

当前任务包与回调 envelope 使用 `schema_version: 2`；适配器必须声明支持的版本和升级路径，未知版本返回 `schema_unsupported`。

## Host adapter boundary

宿主适配层是传输、身份、生命周期、持久化和唤醒桥接，不是项目语义验收者。它必须提供或明确拒绝以下能力：项目/计划解析、解析/创建/复用真实会话、原子派发、基于宿主身份或注册会话的来源认证、事件持久化与去重、父会话唤醒、超时与恢复查询、领导租约和取消代次。能力预检按派发和清理阶段分别执行；只有当前阶段所需能力齐备时返回 `ready`。逻辑记录可落在现有权威存储中，不要求建立第二个任务数据库。详细接口与最小记录见 [references/host-adapter.md](references/host-adapter.md)。

适配器必须知道项目、计划、快照、任务、尝试、代理实例、角色、父子链、状态、交付物引用、回调目标、租约和事件顺序；不必读取完整推理或判断领域结果是否正确。内部子代理可以由父运行时本地接收结果，但仍须拥有可去重的 `target_session_id` 和可恢复收据；宿主只需接收父代理汇总的正式回调。独立主会话必须向宿主发送正式终态。

适配器还必须验证任务契约哈希、计划代次、依赖上下文和父子权限边界；子任务不能声明超出父会话的权限边界。事件处理必须重新检查任务/会话租约，取消和未知事件只能由授权父代理或适配器产生。接管还必须由宿主核验旧、新规范会话身份，持久化交接收据，以代次与租约阻止双重领导；缺少这些能力时不能声称跨会话接续完成。参考的 Codex app-server 绑定见 [references/host-adapter.md](references/host-adapter.md) 和 `scripts/app_server_bridge.py`；它把真实 `thread/*`/`turn/*` 调用接入状态机，持久线程通过 `thread/read` 回读，临时线程通过实时 `item/*`/`turn/*` 通知回读，支持幂等回调生成、stdio 断线重连和有界生命周期监督。临时线程的结果只在当前连接的通知账本中可恢复，重启后必须进入恢复核对，不能假定完成。该桥接不替代项目租约或验收权威。要求接入当前桌面连接时，先用 `DesktopHostSnapshot`/`probe_desktop_host()` 做共享端点预检；私有 stdio、未认证 durable websocket 或未声明为 app-server 的 IPC 必须返回 `capability_gap`，不得把独立进程当作当前桌面会话。

适配器在回调认证、持久化和去重完成后才唤醒父代理。超时、进程异常退出、会话丢失或没有终态回调时只能报告 `unknown`；`unknown` 会封口当前 attempt，迟到事件标为 `stale`，不得让原 attempt 复活。涉及未知外部副作用时，重试前必须先由总指挥完成状态核对和风险决定。

如果当前平台没有目标类型所需的真实能力，应返回 `capability_gap` 和能力预检收据，不写 `task.dispatched`，不把界面空闲、进程退出、普通文本或旋转图标当作完成证据。

`task.completed_claim` 结束的是当前执行尝试的工作声明，不会自动销毁长期主会话。独立验收只有在任务需要独立上下文、权限、证据来源或验收责任时才创建；否则由总指挥或一次性内部子代理完成门禁。一个 attempt 只能有一个 `accepted`/`rejected` 决策；拒绝后的重新执行必须使用新的 attempt 和新的验证范围。

## Composition Contract and guardrails

可单独使用；与其他 Skill 组合时只交换 `request_id`、`status`、`scope`、`evidence_refs`、`next_action`、`budget` 和有来源的计划/快照/回执引用。组合摘要的 `status` 与任务事件的 `status` 是不同层级：摘要不能替代原始回执、授予权限或把 `completed_claim` 升级为 `accepted`。本合集的 `skills/project-agent-orchestrator` 是维护源码；安装目录是运行副本。

- `bootstrap-codex-project` 负责项目文件、计划权威和 `on_complete`；本 Skill 不创建第二份项目计划。
- `durable-context` 负责跨会话检查点和恢复；本 Skill 传递带快照、代次和事件引用的检查点，不替代其恢复账本。
- `human-centered-reasoning-guard` 负责身份、证据和完成声明的门禁；内部子代理的成功不能直接升级为项目成功。
- `execution-reliability` 负责 Windows、进程、端口、运行实例和重试边界；本 Skill 不凭运行状态猜测任务语义。
- `deliberate-project` 只在用户明确调用时提供只读审议；多代理编排不自动触发三堂会审。
- 配套 Skill 缺席时沿用当前项目的权威文件和父代理的普通能力，并标明证据或恢复缺口；真实宿主能力缺席仍返回 `capability_gap`，不得用摘要或模拟接口代替派发。
- 创建主会话、唤醒会话、发送外部消息、修改仓库、部署或其他外部副作用都必须有明确目标、当前授权、可回滚或停止条件。
- 不自动安装框架、启动常驻 Broker、建立第二任务数据库，或把原始聊天记录当作权威状态。
