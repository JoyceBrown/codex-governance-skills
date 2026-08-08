# Durable Context

面向 Codex 的项目级持久上下文技能。它解决的不是“把所有聊天永久保存”，而是让长任务在新会话、上下文压缩、暂停后继续和跨工作台读取时，始终围绕同一份可验证的项目状态工作。

## 核心能力

- 项目本地 `.agent-context/` 作为唯一事实源。
- 自动恢复当前目标、路线、验收标准、约束和下一步。
- 通过 requirements revision、内容哈希和 checkpoint 防止旧需求覆盖新需求。
- 在压缩前后校验 task ID、checkpoint、revision 和 requirements hash。
- 对项目写入执行一致性守卫；账本无效或需求版本未推进时拒绝写入。
- 通过 Obsidian 做可验证的只读投影，通过 Context MCP 提供跨工作台只读读取。
- Hook 日志只记录脱敏的事件、结果、延迟和状态元数据，不记录原始 prompt、工具参数、转录或凭据。

## 设计原则

1. Ledger 优先：`.agent-context` 是当前任务状态，Obsidian 和 MCP 都不能覆盖它。
2. 单写者：语义需求、决策和 checkpoint 由技能生命周期写入，外部接口默认只读。
3. 先验证再恢复：压缩摘要、旧 handoff 或检索结果都不能单独作为事实来源。
4. 自动路由：用户不需要记命令；Skill 和 Codex Hook 根据任务状态自动选择恢复、校验和检索路径。
5. 证据门控：没有真实的并发写入、检索规模或延迟证据时，不引入常驻服务、SQLite 或写入型 MCP。

## 目录

```text
SKILL.md                 Codex 技能说明与自动路由规则
agents/openai.yaml       Codex 技能显示信息和隐式调用策略
scripts/context_state.py 项目账本、revision、checkpoint 和一致性校验
scripts/codex_hook.py    SessionStart、UserPromptSubmit、PreToolUse、PreCompact、PostCompact、Stop Hook
scripts/context_mcp.py   只读 Context MCP（stdio）
scripts/obsidian_bridge.py Obsidian 投影与受控检索
references/              MCP、Obsidian、故障模式和检索选择说明
examples/                脱敏后的 Hook 和 MCP 配置模板
```

## 安装为 Codex 技能

把仓库目录复制到 Codex 技能目录：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.codex\skills\durable-context'
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -Recurse -Force .\* $skillRoot
```

安装后重新打开 Codex 会话。复杂任务、可能被压缩的任务和暂停后继续的任务会自动使用本技能，不需要用户手动输入命令。

## Codex Hook

`examples/hooks.json` 是脱敏模板。将其中的脚本路径替换为安装后的绝对路径，再合并到用户级 `~/.codex/hooks.json`。首次启用或修改 Hook 定义后，需要在 Codex 的 `/hooks` 页面逐项审核并信任；本项目不绕过 Codex 的 Hook trust。

建议启用的事件：

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PreCompact`
- `PostCompact`
- `Stop`

Hook 是机械守卫，不负责猜测语义需求。需求变化仍由技能生命周期记录到当前 ledger。

## Context MCP

`examples/context-mcp.json` 提供只读 stdio MCP 模板。它只允许读取指定项目根目录，并暴露：

- `get_current_context`
- `search_context`
- `get_context_health`
- `list_context_projects`

MCP 没有写入、checkpoint 或任务切换接口。所有语义写入必须回到本地 ledger 生命周期。

## Obsidian

Obsidian 是投影层，不是权威记忆库。默认路径仍可通过 `--vault` 指定；建议在不同机器上显式传入 Vault 路径，或设置环境变量：

```powershell
$env:DURABLE_CONTEXT_VAULT = 'E:\path\to\上下文系统'
```

同步前会拒绝不一致或未 checkpoint 的 ledger。检索默认排除历史、superseded、needs-review、observed 和校验失败的页面。

## 自测与验证

在仓库根目录运行：

```powershell
py -3 .\scripts\context_state.py self-test
py -3 .\scripts\context_mcp.py --self-test
py -3 .\scripts\obsidian_bridge.py self-test
py -3 -m py_compile .\scripts\context_state.py .\scripts\codex_hook.py .\scripts\context_mcp.py .\scripts\obsidian_bridge.py
```

验证真实项目 ledger：

```powershell
py -3 .\scripts\context_state.py --root 'C:\path\to\project' verify
```

## 已知边界

- 它不是完整聊天转录库，也不会自动保留所有对话细节。
- 语义检索目前以结构化 ledger 和受控文本检索为主，不等同于向量数据库或 RAG 平台。
- ledger 是单写者模型；多个工作台默认通过只读 MCP 共享状态。
- Hook 信任、沙箱权限和模型服务响应延迟属于宿主环境，不能由本技能完全控制。

## 安全说明

不要把以下内容提交到 GitHub：`.agent-context/`、`hook-events.jsonl`、个人 Obsidian Vault、完整聊天记录、API key、密码、客户数据或本机截图。仓库提供的配置仅为模板，项目路径和 Vault 路径应按安装环境配置。
