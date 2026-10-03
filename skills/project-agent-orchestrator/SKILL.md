---
name: project-agent-orchestrator
description: Run explicitly enabled PAO work in the current project session with one plan authority, optional bounded internal helpers, and direct verification. Legacy cross-session orchestration is archived and never a prerequisite.
---

# Project Agent Orchestrator

本版本的 PAO 是当前会话内的项目执行模式。它用于让一个长任务在同一会话中按项目计划持续推进，并在中断后从项目文件和验证结果恢复。项目计划、当前代码和测试是事实源；本 Skill 不建立第二套项目状态。

## 开启与关闭

PAO 默认关闭。只有用户明确输入以下任一指令才开启：

- 开启 PAO 模式
- /pao on

用户输入以下任一指令后关闭：

- 关闭 PAO 模式
- /pao off

每次最终回复单独注明：本次任务运行模式：PAO 或 本次任务运行模式：非 PAO。开启 PAO 不要求创建新聊天、等待其他聊天、外部宿主、持续服务或人工确认。

## 权威和执行权

- 项目根目录的 PLANS.md 是唯一持续执行计划；只有 status: active 且 authority: exclusive 的计划可以授权开发。
- 当前会话直接执行计划中的当前任务，并拥有该任务的实现、验证和进度记录责任。
- docs/roadmap.md 只描述方向，docs/work/current.md 只记录进度和证据；二者不能产生第二个任务来源。
- 用户最新明确指令优先，但需求变化仍须在 PLANS.md 中记录为 task_adjustment、priority_branch 或 roadmap_change。
- 计划完成后遵循 on_complete；当前任务未满足完成条件时不得把部分进度宣布为完成。

## 工作流程

1. 读取项目根、PLANS.md、当前进度和相关实现，核对唯一 active/exclusive 计划及唯一 in_progress 任务。
2. 将用户任务压缩为目标、范围、非目标、验收、输出、权限、依赖和停止条件；在计划变化时先更新计划权威。
3. 在当前会话直接实现最小可运行切片，保持既有模块边界、数据不变量和研究采用门禁。
4. 为正例、反例、失败、恢复和用户可见路径补充必要验证；测试通过不自动掩盖尚未验证的外部副作用。
5. 更新项目收据和 docs/work/current.md，说明改动、证据、剩余风险和下一动作。
6. 最终核对工作区、测试结果和用户成功状态，并按本文件标注 PAO 模式。

## 可选内部辅助

当前会话可以创建短期、边界明确的内部子代理来做只读审计、测试或证据整理。子代理没有计划权威，也不能改变范围、完成条件、研究边界或发布状态。没有子代理、子代理不可用或子代理结果不完整，都不阻塞当前会话；父会话必须复核其结果后再使用。

## 中断恢复

恢复时重新读取 PLANS.md、当前代码、工作区状态、最近收据和测试结果，比较当前事实后继续。不要等待已经丢失的聊天，不要重放结果不明的副作用，不要把历史聊天、缓存或隐藏账本当作当前授权。若当前任务状态不明，先做只读核对并将结果写入当前收据，再决定继续、回退或停止。

## 失败和停止

失败时保留原始数据和收据，标记适用的 failed、unknown、stale、lagging 或 rebuild_required 状态，停止扩大影响，完成对账后再重试。所有循环、重试、并发和外部写入都必须有明确终止条件。缺少可选工具时在收据中记录能力缺口，但不把它升级为当前会话开发门禁。

## Composition Contract

## 组合边界

- bootstrap-codex-project 负责项目文件、计划权威和 on_complete。
- durable-context 负责跨会话检查点和恢复账本；本 Skill 只引用其证据，不建立第二个账本。
- human-centered-reasoning-guard 负责目标、身份、证据和完成声明门禁。
- execution-reliability 负责 Windows、Git、进程和有限重试核验。
- 其他 Skill 只通过目标、范围、证据、状态和下一动作交换摘要，不改变项目计划。

## 旧资料

references/ 和 scripts/ 中的跨会话协议、适配器和回归夹具仅作为历史兼容资料保存，不属于本 Skill 的执行规则。它们不得被引用来要求额外聊天、外部投递、回调、租约或独立验收；项目计划和当前会话直接验证优先。

## 输出合同

最终回复至少说明：

- 当前计划和任务；
- 已完成的实现或治理修复；
- 验证命令及结果；
- 未完成项或已知非阻塞误报；
- 本次任务运行模式：PAO。
