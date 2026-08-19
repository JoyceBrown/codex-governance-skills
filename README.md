# Codex 治理与工程 Skills

这是一个面向 Codex 的中文 Skill 集合，目标是让长任务能够恢复正确基线，让软件变更先验证真实目标，再用最小成本完成诊断、测试和架构检查。

本仓库包含 4 个成熟治理 Skill 和 5 个轻量原子工程 Skill。每个 Skill 都可以单独使用；组合时只交换有限的结构化摘要，不复制聊天记录、不建立第二套项目事实源、不自动安装或运行陌生能力。

## 内容状态

| 类别 | Skill | 主要责任 | 默认副作用 |
| --- | --- | --- | --- |
| 治理 | `bootstrap-codex-project` | 项目事实、文件权责、活动计划和迁移 | 依据用户授权生成项目文档 |
| 治理 | `durable-context` | 跨会话恢复、基线漂移、有限检索和只读 Context MCP | 维护项目本地账本 |
| 治理 | `human-centered-reasoning-guard` | 事实门禁、目标门禁、身份、回滚和完成验证 | 默认阻止未经验证的高风险写入 |
| 治理 | `deliberate-project` | 显式调用的多角度、证据驱动只读审议 | 不修改项目；经验目录另有明确授权时才写入 |
| 原子 | `intent-alignment` | 把模糊请求压缩为目标、成功状态、范围和未知 | 只读 |
| 原子 | `diagnose` | 竞争根因、复现路径、区分性检查和证据链 | 只读，除非用户另行授权修复 |
| 原子 | `tdd-loop` | 红-绿-重构、回归、用户路径验证和测试成本控制 | 只修改授权范围内的代码/测试 |
| 原子 | `architecture-health` | 模块边界、依赖、接口、漂移、容量和回滚检查 | 只读审查 |
| 原子 | `capability-director` | 判断能力错配，比较有限候选并输出薄 Receipt | 只读；不安装、不启用、不执行陌生能力 |

四个现有 Skill 的源码来自各自公开仓库的已核验 `main` 版本；本整合仓库只保留源码和公开文档，不包含项目账本、Hook 日志、凭据、聊天记录、运行时缓存或用户项目源码。当前不附带许可证，因为许可证选择需要用户明确决定。

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
写入、外部副作用或完成声明 -> human-centered-reasoning-guard
能力明显错配         -> capability-director（只读候选诊断）
用户明确“三堂会审”   -> deliberate-project（显式、只读）
```

`human-centered-reasoning-guard` 可以在执行前、执行中和完成前重复作为门禁；它不是最后一道流水线步骤。`bootstrap-codex-project`、`durable-context` 和 `deliberate-project` 都有自己的触发边界，缺少对应信号时不应强行加入流程。

`capability-director` 只在当前能力明显不匹配时建议“使用、借鉴、Fork、安装或拒绝”。它先检查项目已有能力和 Codex 原生能力，最多给出 3 个候选，并记录问题、范围、来源和结论；它不会自动下载、修改配置、授予权限或启动插件运行时。

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

安装整个集合时，先克隆本仓库，再运行自带安装器。它默认拒绝覆盖同名 Skill；显式使用 `-Force` 时先把旧目录移动到时间戳备份，再安装新目录。安装器不使用镜像删除，也不会改 Codex 配置、Hook 或 MCP。

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
这个测试失败了。先列出至少两个竞争根因，给出最便宜的区分性检查，再决定是否修复。
```

```text
继续这个项目。先恢复当前账本和基线，确认计划没有漂移，然后用最小 TDD 回路修复并验证原始用户路径。
```

```text
三堂会审：审查这次跨模块迁移，保留竞争判断，最后只报告证据缺口和下一步检查。
```

## 验证

在仓库根目录运行：

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 "$env:CODEX_HOME\skills\.system\skill-creator\scripts\quick_validate.py" .\skills\intent-alignment
.\scripts\install.ps1 -TargetSkillsRoot (Join-Path $env:TEMP 'codex-skills-smoke')
.\scripts\validate-repository.ps1
```

测试会检查 9 个 Skill 的入口、YAML 元数据、组合合同、敏感文件排除和公开仓库结构。四个成熟 Skill 的原始测试仍保留在各自目录中，可按各目录 README 或 `tests/` 运行。`pytest` 若未安装，不代表 unittest 或 Skill 结构校验失败。

## 旧仓库处理

旧仓库的删除不是安装步骤，也不是本仓库自动行为。必须先核对新仓库远端 URL、默认分支、提交内容、安装结果和权限边界，再由用户明确确认具体要删除的仓库名。

## 来源版本

本次整合基线：

- `bootstrap-codex-project`: `17a7d09bbef60c27461923916d709fc3175308a0`
- `durable-context`: `ae3ae6d1e1d9e884a2d73ff33cf9b17d8573d3c9`
- `human-centered-reasoning-guard`: `ba665fc4fb0ab4ae96bcb889434a5b42ccee4e3e`
- `deliberate-project`: `b167dce30a46ff50bd321b69df52d9b37cf041c6`

四个入口在上述基线上增加了最小组合合同；其余核心实现和测试保持来源版本结构。
