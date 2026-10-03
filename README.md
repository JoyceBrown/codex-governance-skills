# Codex 治理与工程 Skills

这是一个面向 Codex 的中文 Skill 集合，目标是让长任务能够恢复正确基线，让软件变更先验证真实目标，再用最小成本完成诊断、测试和架构检查。

本仓库包含 5 个治理 Skill 和 6 个轻量原子工程 Skill。每个 Skill 都可以单独使用；组合时只交换有限的结构化摘要，不复制聊天记录、不建立第二套项目事实源、不自动安装或运行陌生能力。

## 内容状态

| 类别 | Skill | 主要责任 | 默认副作用 |
| --- | --- | --- | --- |
| 治理 | `bootstrap-codex-project` | 项目事实、文件权责、活动计划和迁移 | 依据用户授权生成项目文档 |
| 治理 | `durable-context` | 跨会话恢复、基线漂移、有限检索和只读 Context MCP | 复杂任务维护项目本地账本；普通问题不建账 |
| 治理 | `human-centered-reasoning-guard` | 事实门禁、目标门禁、身份、回滚和完成验证 | 只约束被调用的具体高风险动作，不阻断普通会话 |
| 治理 | `deliberate-project` | 显式调用的多角度、证据驱动只读审议 | 不修改项目；经验目录另有明确授权时才写入 |
| 治理 | `project-agent-orchestrator` | 当前会话内的项目计划执行、恢复和可选内部辅助 | 仅在用户显式开启后运行；不创建额外会话或外部服务 |
| 原子 | `intent-alignment` | 把模糊请求压缩为目标、成功状态、范围和未知 | 只读 |
| 原子 | `diagnose` | 竞争根因、复现路径、区分性检查和证据链 | 只读，除非用户另行授权修复 |
| 原子 | `tdd-loop` | 红-绿-重构、回归、用户路径验证和测试成本控制 | 只修改授权范围内的代码/测试 |
| 原子 | `architecture-health` | 模块边界、依赖、接口、漂移、容量和回滚检查 | 只读审查 |
| 原子 | `capability-director` | 判断能力错配，比较有限候选并输出薄 Receipt | 只读；不安装、不启用、不执行陌生能力 |
| 原子 | `execution-reliability` | 执行环境、目标、产物、进程和有限重试核验 | 无全局 Hook；普通任务 fail-open，高风险动作才阻断 |

前四个成熟 Skill 首次从各自公开仓库的已核验 `main` 版本导入；`project-agent-orchestrator` 是本合集原生维护的第五个治理 Skill。导入或创建完成后，本合集的 `main` 和 `skills/<name>` 是唯一长期维护权威。旧仓完整历史保存在本合集的 `legacy/<skill>/main` 标签中，`docs/source-manifest.json` 同时记录原 URL、提交和归档引用，旧 URL 不再作为上游。本仓库不包含项目账本、Hook 日志、凭据、聊天记录、运行时缓存或用户项目源码。当前不附带许可证，因为许可证选择需要用户明确决定。

## 怎么组合

正常入口仍然是自然语言。Codex 根据任务选择需要的 Skill，不要求用户记住内部协议。

```text
按任务信号选择能力，不是固定流水线：

新建或治理项目       -> bootstrap-codex-project
长任务或跨会话       -> durable-context
目标模糊             -> intent-alignment
根因不清或结果未变   -> diagnose
代码/测试变更         -> tdd-loop
结构、依赖或容量疑问 -> architecture-health
执行、构建、安装、进程或 UI 易出错 -> execution-reliability
写入、外部副作用或完成声明 -> human-centered-reasoning-guard
项目长任务直接执行和恢复       -> project-agent-orchestrator
能力明显错配         -> capability-director（只读候选诊断）
用户明确“三堂会审”   -> deliberate-project（显式、只读）
```

`human-centered-reasoning-guard` 可以在执行前、执行中和完成前重复作为门禁；它不是最后一道流水线步骤。`bootstrap-codex-project`、`durable-context`、`deliberate-project` 和 `project-agent-orchestrator` 都有自己的触发边界，缺少对应信号时不应强行加入流程。

Guard 已增量接入 HCR 6.2 的 WHY/WHAT/HOW、认识论状态、结构推理和零 LLM Cognitive Replay。唯一入口仍为 `human-centered-reasoning-guard`，原事实门、目标门、身份、回滚、完成验证和单账本桥接继续负责原有边界。深层认知按事件触发；Replay 只读取经授权的经验投影，筛选项目、环境、约束和有效性后输出历史候选，不能批准执行或写成当前事实。缺少结构化历史时正常回到当前证据，不要求安装宿主、Hook 或数据库。来源、修复和功能映射见 [接入说明](docs/hcr-6.2-integration.md)。

当你主动要求“从用户角度重新思考这个需求”时，`human-centered-reasoning-guard` 会进入主动用户视角模式：先暂停技术实现，重建“问题触发 -> 用户任务 -> 期望体验 -> 可见成功 -> 失败恢复”的路径，区分事实、假设和未知，再给出 `CONTINUE / REFRAME / ASK / STOP`。默认停在只读理解结果，不会因为你提到一个功能名就直接改代码。确认理解后再说“继续实现”，才进入正常的授权、事实门和验证流程。

`capability-director` 只在当前能力明显不匹配时建议“使用、借鉴、Fork、安装或拒绝”。它先检查项目已有能力和 Codex 原生能力，最多给出 3 个候选，并记录问题、范围、来源和结论；它不会自动下载、修改配置、授予权限或启动插件运行时。

`execution-reliability` 是执行层配套 Skill。它在构建、安装、发布、Windows 命令、路径、环境变量、Git、进程和 UI 自动化出现风险信号时做最小预检和后置核验；同一动作最多自动重试一次，状态未知先检查。它不拥有计划、记忆、授权或“三堂会审”，不注册全局 Hook，也不把一次错误自动升级为永久规则。

`project-agent-orchestrator` 负责在当前会话中按唯一项目计划推进长任务、恢复中断、记录验证和管理可选的短期内部辅助。用户显式开启后立即可用；缺少外部宿主、额外聊天或辅助代理不影响当前会话开发。`references/` 与 `scripts/` 中的跨会话材料仅保留作历史兼容资料，不是本 Skill 的启动条件或完成门禁。

## 组合信封

组合只传递以下有限字段，具体 Skill 仍保留自己的权威边界：

```json
{
  "request_id": "turn-or-task-id",
  "status": "FOUND | PARTIAL | NOT_FOUND | CONFLICTED | BLOCKED_UNCERTAINTY",
  "scope": "project or task scope",
  "intent_status": "DECIDED | ASSUMED | OPEN | CONFLICTED",
  "evidence_refs": ["finding-or-test-id"],
  "next_action": "continue | targeted_check | ask | stop",
  "budget": {"chars": 3000, "checks": 3}
}
```

摘要不是事实源。项目文件、当前代码、测试结果、`requirements.md`、`PLANS.md` 和 `.agent-context` 的权责仍按对应治理 Skill 执行。没有某个可选 Skill 时，其他 Skill 使用自己的 standalone fallback，并把真正影响结果的缺口标为 `Open`，不会递归搜索或创造新记忆库。

## 安装

安装整个集合时，先克隆本仓库，再运行自带安装器。它默认拒绝覆盖同名 Skill；显式使用 `-Force` 时先把旧目录移动到 `skills` 根目录之外的时间戳备份，再安装新目录，避免备份副本被发现为活动 Skill。安装器不使用镜像删除，也不会改 Codex 配置、Hook 或 MCP。

```powershell
git clone <新仓库地址> codex-governance-skills
Set-Location codex-governance-skills
.\scripts\install.ps1
```

安装到临时目录或自定义位置：

```powershell
.\scripts\install.ps1 -TargetSkillsRoot 'D:\temp\codex-skills'
```

覆盖已有同名 Skill 并保留备份：

```powershell
.\scripts\install.ps1 -Force
```

安装后重新打开 Codex 或刷新 Skill 列表。`deliberate-project` 只有用户明确输入 `$deliberate-project` 或“三堂会审”时才激活；其他 Skill 按其描述自动选择。

## 使用示例

```text
帮我把这个需求压缩成可验收的目标，指出范围和未知，不要修改代码。
```

```text
调用 Human Guard，从用户最终结果重新理解这个需求，先不要改代码。
```

```text
这个测试失败了。先列出至少两个竞争根因，给出最便宜的区分性检查，再决定是否修复。
```

```text
继续这个项目。先恢复当前账本和基线，确认计划没有漂移，然后用最小 TDD 回路修复并验证原始用户路径。
```

```text
开启 PAO，按项目计划在当前会话直接推进；必要时使用有界内部辅助，并在本会话完成验证和收据。
```

```text
三堂会审：审查这次跨模块迁移，保留竞争判断，最后只报告证据缺口和下一步检查。
```

## 验证

在仓库根目录运行：

```powershell
.\scripts\validate-repository.ps1
.\scripts\install.ps1 -TargetSkillsRoot (Join-Path $env:TEMP 'codex-skills-smoke')
```

验证脚本会运行合集合同测试、各 Skill 的内嵌 Python 测试、`project-agent-orchestrator` 的宿主适配器回归、human-centered guard 的 PowerShell 回归测试，以及本机可用时的全部 `quick_validate.py`。仓库合同还检查 Git 路径分隔符和待发布文本 blob 的 UTF-8/LF 规范，防止首次远端提交的问题回归。

验证还包含 Guard 的 Python Replay/离线 Schema 回归和真实示例输入输出契约。运行 `python -X utf8 skills/human-centered-reasoning-guard/validate_package.py` 可单独核对新增资源与示例。程序验证证明本地工具与合同可用；真实任务中的用户收益仍需独立验收。

## 旧仓库处理

只有本合集是长期维护权威。旧 URL 仅作为 `legacy_import` 迁移证据，完整旧历史由清单中的 `archive_ref` 保留；安装、开发和发布都不得再依赖旧仓库。删除旧仓库仍不是安装器的自动行为，必须先核对合集远端、默认分支、提交内容、归档引用、安装结果、回滚点和删除权限。

## 来源版本

本次整合基线：

- `bootstrap-codex-project`: `17a7d09bbef60c27461923916d709fc3175308a0`
- `durable-context`: `c903603a62e2bcf05491f1be562bf2b440c1c017`，并加入只读合集审计器及其测试
- `human-centered-reasoning-guard`: `ba665fc4fb0ab4ae96bcb889434a5b42ccee4e3e`
- `deliberate-project`: `b167dce30a46ff50bd321b69df52d9b37cf041c6`

第五个治理入口 `project-agent-orchestrator` 为本合集原生实现；其来源、宿主边界和修复后的协调/投递/回执能力见 `docs/source-manifest.json` 与 [组合说明](docs/composition.md)。五个治理入口保留各自的组合合同；`deliberate-project` 的仓库级测试和夹具、`project-agent-orchestrator` 的宿主适配器测试已适配到合集目录。后续变更只在本合集维护。
