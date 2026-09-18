---
name: execution-reliability
description: 在 Windows、命令行、electron-builder/桌面打包、产品变体、安装、Git、进程或 UI 自动化容易反复出错时，执行有界的环境预检、目标确认、验证、重试控制和短收据；不接管项目治理、记忆、授权或三堂会审。
---

# Execution Reliability

这是执行层的窄 Skill，用来减少“命令看似成功但目标错了”“环境变量只传了一层”“构建后才发现包名或版本不对”“旧进程或旧产物被误认为当前结果”“同一失败命令反复重跑”等共性错误。

## 何时自动使用

根据任务信号按需路由，不要求用户记内部命令：

- 涉及 Windows PowerShell/CMD、中文或长路径、编码、权限、环境变量、Node/npm/pnpm、锁文件、Git worktree、端口、watcher、旧服务、桌面 UI 自动化；
- 构建、打包、安装、发布、替换、删除、重启或外部状态改变；
- 用户报告“发出去没反应”“刚才改了但结果没变”“重试仍失败”，或任务在中断后恢复。

普通问答、单文件小改动和已由更可靠工具直接验证的低风险操作，不启动完整预检。

## 工作协议

1. **先分级**：`observe`（只提示）、`verify`（需要目标和结果证据）、`gate`（高风险动作需要明确确认）。只有 `verify/gate` 才运行脚本。
2. **确认身份**：记录当前工作目录、真实项目根、Git 分支/提交（若适用）、源码根、目标路径、目标类型和预期版本。路径含中文不是自动错误；无法解析、过长、跨仓库或目标不明才升级风险。
3. **做最小预检**：只检查会影响当前动作的环境。Windows 命令优先使用明确的 PowerShell 参数和 `-LiteralPath`；环境变量在启动构建器的同一进程中设置；不要把只传给 Electron 的变量误当成传给 electron-builder。
4. **变体先门禁**：如果项目存在 Candidate、staging、release 或其他产品变体，禁止直接执行没有明确身份参数的通用 `build/package` 命令。优先寻找项目专用包装器；若只有依赖环境变量的裸命令，先输出 `BLOCKED` 并要求显式 flavor、同进程变量和独立输出目录。`allow_implicit_invocation` 只允许路由，不是命令拦截器。
   - 对 `electron-builder` 或桌面安装包请求，先读取 `package.json` 和构建配置，执行项目提供的 `--check`/身份检查；检查未通过前不得启动构建器。
   - 若项目同时产出不同产品名，必须把 flavor、环境变量、`appId`/`productName`、artifact 名称和输出目录作为同一条路由确认；只看到 Renderer 构建成功不能视为打包身份已生效。
5. **执行一次**：保存可复核的动作标签、目标指纹和退出状态，不把完整命令行、凭据或日志复制进收据。
6. **验证后再声明**：目标存在且类型正确；构建产物的文件名、版本、`appId`/包元数据和 SHA256 与预期一致；运行验证要区分源码、构建目录、安装目录和当前进程。
7. **有限重试**：同一目标、同一状态、同一动作最多自动重试一次。状态未知、目标指纹变化、进程所有权不明或高风险动作失败时停止并检查，不盲目重跑。修复后必须改变输入或状态并重新确认。
8. **输出短收据**：只返回 `READY/WARN/BLOCKED`、检查 ID、证据引用、一次重试结论和下一步；不得生成第二套项目账本、Hook、常驻服务或全量日志。

详细规则按需读取：

- [风险规则](references/risk-rules.md)：每条规则的触发、风险、前后条件、重试和来源字段。
- [Windows 与路径](references/windows-and-paths.md)：PowerShell、编码、中文/长路径和变量传播。
- [构建与产物](references/build-and-artifact.md)：源码/构建/安装身份和包元数据核验。
- [Git、进程与 UI](references/git-process-ui.md)：仓库、端口、旧进程和页面状态。
- [收据格式](references/receipt-schema.md)：短、可引用、不过度持久化的输出格式。
- [recipes/](recipes/)：只在对应动作发生时读取的执行配方。

## 与治理 Skill 联动

本 Skill 没有需求、计划、记忆或授权所有权，也不写 `.agent-context`，不注册全局 Hook，不启动 Obsidian/MCP，不自动调用“三堂会审”。

- `bootstrap-codex-project` 判断项目是否需要执行可靠性能力；本 Skill 不改项目治理文件。
- `human-centered-reasoning-guard` 负责真实用户目标、授权、回滚和最终用户路径；其门禁优先。
- `durable-context` 只接收本 Skill 的收据引用、目标指纹和恢复摘要，不接收原始命令或日志。
- `diagnose` 负责竞争根因；本 Skill 提供环境和执行证据，不把一次失败直接升级为永久规则。
- `tdd-loop` 负责代码测试闭环；本 Skill 负责测试前后的执行身份和产物核验。
- `deliberate-project` 只在用户明确“三堂会审”或 `$deliberate-project` 时进行只读深审；本 Skill 只能产生 `review_candidate: NONE|POSSIBLE|REQUIRED`，不得触发它，二者禁止互相调用。

## Composition Contract

对外只交换有限结构化字段：

```json
{
  "request_id": "turn-or-task-id",
  "status": "READY | WARN | BLOCKED | PARTIAL",
  "scope": "current action scope",
  "risk": "low | medium | high | critical",
  "target": "redacted target label",
  "evidence_refs": ["check-id-or-artifact-digest"],
  "retry": "not-needed | allowed-once | stopped | ask",
  "review_candidate": "NONE | POSSIBLE | REQUIRED",
  "next_action": "one smallest safe action",
  "budget": {"checks": 3, "chars": 2400}
}
```

字段没有证据时标为 `Open`；不传原始提示、完整命令、凭据、聊天记录、账本内容或私有源码。脚本是无状态辅助器，默认只输出 JSON；需要落盘时由调用方明确给出目标路径，且不能把它当作项目计划或第二任务数据库。

## 不阻断的条件

普通任务采用 fail-open：预检失败只报告 `WARN`，除非动作属于安装、发布、删除、替换、迁移、重启、权限或生产外部状态。高风险动作在目标身份、授权、回滚点或关键产物不明确时必须 `BLOCKED`。
