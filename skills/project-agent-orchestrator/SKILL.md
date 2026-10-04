---
name: project-agent-orchestrator
description: Run explicitly enabled PAO work in the current project session with one plan authority, bounded continuous development, optional internal implementation helpers, structured recovery receipts, and direct verification. Legacy cross-session orchestration is archived and never a prerequisite.
---

# Project Agent Orchestrator

本版本的 PAO 以当前会话和唯一项目计划为执行权威。它连续实现可验证切片，使用有限的内部助手和自动修复，并在中断后从项目文件和验证结果恢复。可选的 `scripts/app_server_bridge.py` 只在宿主明确提供真实 app-server 能力时使用；它是开发增强通道，不是 PAO 启动条件，也不拥有项目事实或授权。项目计划、当前代码、测试和收据是事实源；本 Skill 不建立第二套项目状态。

## 开启、开发和关闭

PAO 默认关闭。只有用户明确输入以下任一指令才开启：

- 开启 PAO 模式
- `/pao on`
- `/pao develop`

模式含义：

- `pao`：按当前计划执行一个或多个安全切片，完成本轮验证后收口。
- `pao_develop`：在同一 turn 内持续执行开发队列，直到队列完成、真实阻塞、预算耗尽或达到固定停止点；代码任务中“开启 PAO”默认采用此档位，用户明确要求只分析或审查时采用 `pao`。

用户输入以下任一指令后关闭：

- 关闭 PAO 模式
- `/pao off`

关闭后不得继续使用 PAO 的计划推进、内部助手派发或连续开发规则。默认 PAO 不创建独立聊天、不启动后台服务、不保证 turn 结束后自动发起下一 turn；只有用户另行要求且宿主能力探测通过时，才启用可选 bridge 的短期任务线程。

## 权威和执行权

- 项目根目录的 `PLANS.md` 是唯一持续执行计划；只有 `status: active` 且 `authority: exclusive` 的计划可以授权开发。
- 当前会话直接执行计划中的当前任务，并拥有实现、验证、进度记录和阶段推进责任。
- `docs/roadmap.md` 只描述方向，`docs/work/current.md` 只记录进度和证据；二者不能产生第二个任务来源。
- 用户最新明确指令优先；需求变化仍须在 `PLANS.md` 中记录为 `task_adjustment`、`priority_branch` 或 `roadmap_change`。
- 若 `PLANS.md` 提供 `execution_queue`，它是当前任务下的有序开发切片；没有队列时只能依据当前任务的完成条件生成一个可验证的下一切片，并把结果写入既有检查点，不另建任务系统。
- 计划完成后遵循 `on_complete`；当前任务未满足完成条件时不得宣布阶段完成或激活下一阶段。

## Execution Queue Contract

`execution_queue` 是 `PLANS.md` 中当前任务的可选字段，不是第二个计划或账本。每个队列项至少包含 `slice_id`、`status`、`objective`、`done_when` 和 `verify`；`status` 只能是 `pending`、`in_progress`、`completed` 或 `blocked`。同一时刻最多一个 `in_progress`，且必须等于 `current_task_id` 对应任务的当前切片。只有 `done_when` 全部满足、`verify` 有可定位证据并写入既有检查点后，切片才能变为 `completed`；失败或外部状态不明时改为 `blocked`，保留 `stop_reason`，不得跳到下一项。

`current-work.md` 只保存 `last_completed_slice`、`next_slice`、`resume_cursor` 和 `stop_reason` 等恢复投影；它不能授权新任务。队列为空、缺失或与计划冲突时，PAO 回退为当前任务的一个最小可运行切片并标记 `PARTIAL`/`CONFLICTED`，不创建替代队列。接近上下文或工具预算时，先写入这些字段再停止；恢复只从计划、检查点和验证证据重建，不等待旧会话。

## 开发执行循环

在 `pao_develop` 下，按以下循环执行，不因完成一个文件或一个测试就提前结束：

1. 读取项目根、`PLANS.md`、当前进度、最近收据、相关代码和测试；确认唯一 `active/exclusive` 计划及唯一 `in_progress` 任务。
2. 把当前任务变成有序切片：实现目标、依赖、改动边界、验证命令、停止条件和下一切片。
3. 实现最小可运行切片。切片至少同时满足：存在可调用的代码路径、至少一条针对行为的验证、失败状态或边界有明确结果、没有绕过项目既有写入边界。
4. 运行针对性测试；失败时改变输入或代码后最多自动修复两轮。同一失败命令不得在状态不变时重复执行。
5. 若队列仍有下一项且预算允许，继续执行；每完成一个切片更新既有检查点的 `last_completed_slice` 和 `next_slice`。
6. 当前任务的全部完成条件满足后，执行阶段级验证、写入阶段收据，并按 `on_complete` 推进；否则保留 `in_progress`。
7. 接近上下文、工具、时间或重试预算时，先写可恢复检查点，再停止本轮。

“最小可运行切片”不得只写文档或只改类型声明；如果本阶段明确排除运行时，则必须提供隔离 fixture 或契约测试证明边界。研究材料被引用时，必须先确认 adoption 记录、来源哈希和权利状态；`research_only` 只能作为证据，不能直接进入运行时规则、Prompt、PolicyPack 或 Canon。研究覆盖、哈希或权利门禁不满足时，标记 `blocked`/`ABSTAIN` 并停止扩大影响。

## 内部开发助手

当前会话可以创建短期、边界明确的内部助手来增加开发吞吐量，角色可以是：

- `implementer`：实现独立模块或小切片；
- `tester`：补充行为测试、运行回归并整理失败证据；
- `debugger`：针对已复现失败提出最小修复。

内部助手没有计划权威，不能改变范围、完成条件、研究边界、发布状态或当前收据。父会话负责分派、复核、合并和最终验证。互不冲突的任务可以并行；共享文件或同一状态机的任务必须串行，优先使用隔离工作区。助手不可用、结果不完整或返回未知状态都不阻塞父会话，父会话应回到当前切片并记录证据。助手用完即丢，不进入用户可见长期会话列表。

## 中断恢复和有界恢复层级

恢复时先读取 `PLANS.md`、当前检查点、最近收据、当前代码和工作区状态，不等待已经丢失的聊天，不重放结果不明的副作用。恢复状态和停止规则沿用 [durable-context 的唯一词汇表](../durable-context/references/recovery-status.md)，PAO 不另立语义。

固定停止点：一次定向恢复补查、一次外部状态核验、同一修复最多两轮。达到停止点仍不能确认时，保留原始数据和收据，标记 `failed`、`unknown`、`stale`、`lagging` 或 `rebuild_required`，停止扩大影响。

## Composition Contract / 组合边界

本 Skill 的组合消息遵循 `composition-v1`（见 `docs/composition.schema.json`）；独立运行时 `source_skill` 与 `target_skill` 相同、`degradation=standalone`。其 PAO 收据中的 `status`、`run_mode` 是本 Skill 内部输出，映射到组合信封时必须分别填入 `execution_status`、`action_status` 和 `degradation`，不能用一个通用 `status` 代替多个状态域。

- `bootstrap-codex-project` 负责项目文件、计划权威和 `on_complete`。
- `durable-context` 负责跨会话检查点和恢复账本，并维护 [唯一恢复状态词汇表](../durable-context/references/recovery-status.md)；PAO 只消费这些状态，不另立语义，也不建立第二个账本。
- `human-centered-reasoning-guard` 负责目标、身份、证据和完成声明门禁。
- `execution-reliability` 负责 Windows、Git、进程和有限重试核验。
- `tdd-loop` 负责代码测试闭环；本 Skill 负责把测试接入开发队列和阶段推进。
- 其他 Skill 只通过目标、范围、证据、状态和下一动作交换摘要，不改变项目计划。

缺少任何可选协作者时仍按当前计划直接执行安全切片；只有会改变结果的证据缺口才标为 `Open`、`partial` 或 `blocked`。组合调用达到深度、调用次数或字符预算时，写检查点并回退到当前会话的 standalone 开发循环。

## Non-Goals

- 不替代领域调试、安全审查、产品决策或人工授权。
- 不把 commander、租约、跨会话回调、外部宿主或后台守护进程当作当前会话开发的必需条件；可选宿主 bridge 必须经过能力探测、租约 fencing 和明确回执，不能越过本 Skill 的计划、授权和写入边界。
- 不建立第二套项目计划、记忆账本或验收系统。
- 不因每次纠错、每个小切片或每个助手结果无限增加文档和收据。
- 不把测试通过、上下文完整或收据存在误报为产品功能、文学质量或外部副作用已经成功。

## 结构化收据合同

每次最终回复必须提供一份短收据；阶段完成、失败、暂停或恢复时，将同一收据写入项目已有的阶段收据或检查点，不新建第二个账本。字段必须保持稳定：

```json
{
  "plan_id": "<PLANS.md plan_id>",
  "task_id": "<current in_progress task>",
  "status": "completed | in_progress | failed | blocked | unknown",
  "evidence_refs": ["<test, receipt, commit, or checkpoint reference>"],
  "run_mode": "pao | pao_develop | non_pao",
  "next_action": "<one smallest executable action or null>",
  "budget": {
    "slices": 0,
    "tool_calls": 0,
    "retries_used": 0,
    "retry_limit": 2,
    "context": "ok | near_limit | exhausted"
  }
}
```

`evidence_refs` 只能引用真实可定位的测试、收据、提交、检查点或外部状态；没有证据写 `Open`，不得编造。`status=completed` 只表示当前收据覆盖的切片或阶段已满足其完成条件，不代表整个项目完成。`next_action` 必须是一个动作，不写散文计划。预算字段用于限制连续开发、恢复和重试，不要求每次输出完整日志。

执行保证边界：这些字段是 Skill 级协议，不是宿主运行时强制机制。没有宿主回执、钩子或外部验证器时，仓库验证最多检查技能文本和已生成收据的形状，不能证明代理在每个 turn 都实际执行了对应动作。不得把“收据存在”当作运行时行为已经被强制或外部副作用已经成功。

## 可选宿主增强

当用户明确要求使用真实宿主、且 `probe_desktop_host` 找到共享 `unix`/`ws`/`websocket` 端点时，可以读取 [宿主适配说明](references/host-adapter.md) 并使用 bridge 创建短期开发线程。只提供私有 `stdio` 或模拟 transport 时，结果必须是 `capability_gap` 或测试状态，不能声称已接通桌面。宿主事件每次接收都重新核对项目、计划、快照、commander epoch 和租约；旧事件只能进入 `stale`，不能推进当前任务。临时线程完成后必须执行 cleanup preflight 并归档；活动通知 turn 超过内存上限时保留并报告 `recovery_gap`。

## 旧资料

`references/` 中已经淘汰的跨会话协议仍是历史资料；当前 `scripts/host_adapter.py` 和 `scripts/app_server_bridge.py` 是可选宿主增强的实现与回归夹具，不是默认启动条件。不得在没有真实端点和宿主回执时声称外部投递成功；项目计划和当前会话直接验证优先。

## 输出合同

最终回复至少说明：

- 当前计划和任务；
- 本轮完成的开发切片或治理修复；
- 验证命令及结果；
- 未完成项、恢复状态或已知非阻塞误报；
- 本次任务运行模式：PAO、PAO 开发模式或非 PAO。
