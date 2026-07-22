# Bootstrap Codex Project

把一个项目想法或已有仓库，整理成最小、准确、可信、可维护、适合 Codex 长期工作的项目上下文系统。

这个仓库包含一个可安装的 Codex Skill。它不会把项目变成臃肿的“AI 配置包”，也不会为了看起来完整而给每个文件夹生成 `AGENTS.md`。它解决四个问题：

1. 这个项目到底要解决什么问题？
2. 哪些内容已经验证，哪些只是决定、计划、假设或待确认？
3. Codex 修改项目时必须遵守什么规则？
4. 当前任务应该读取哪些文件，而不是把整个仓库塞入上下文？

## 为什么需要它

长项目常见的问题不是没有文档，而是文档越来越多却越来越不可信：

- README 和 `AGENTS.md` 重复项目介绍；
- 每个目录都有 `AGENTS.md`，规则相互覆盖；
- 文档中的命令已经不存在；
- 产品事实、架构决策、临时计划和个人偏好混在一起；
- 采集内容、模型提取和用户结论没有来源或可信状态；
- 一开始就加入 Hooks、Rules、MCP、自定义 Agent，维护配置比维护项目更费劲。

本 Skill 建立的是语义化上下文，不是另一个资料管理器：

```text
项目事实       -> README.md、docs/、代码、测试、CI
Codex 约束     -> 根或必要的嵌套 AGENTS.md
可选能力       -> .codex/、.agents/skills/、MCP、Rules、Hooks 等
```

每个重要事实只有一个权威归属。其他文件只做导航，不复制整段内容。

## 证据状态

当读者可能把意图误认为现实时，文档使用明确状态：

| 状态 | 含义 |
| --- | --- |
| `Verified` | 已从仓库证据或成功执行的命令中验证 |
| `Decided` | 用户或正式项目决策已经确定 |
| `Planned` | 已接受的方向，但还没有实现 |
| `Assumed` | 为继续工作采用的可撤销临时假设 |
| `Open` | 尚未解决的问题或相互冲突的证据 |

文件名、目录名、依赖名称和模型输出不能自动升级为 `Verified`。

## 三种模式

### Greenfield

用户提供项目想法，目标目录为空或尚未创建。Skill 提炼目标用户、问题、首条完整工作流、范围、非目标、技术方向和未决问题。

### Existing repository

项目已有代码或配置。Skill 先只读检查 README、`AGENTS.md`、manifest、包管理器、测试、CI 和文档，再决定需要创建或修改什么。

### Audit or refresh

用于修复过期命令、重复文档、规则覆盖、来源不明、说明与代码矛盾，以及没有真实用途的高级配置。

## 三档输出

### Minimal

适合小型、早期或单模块项目：

```text
README.md
AGENTS.md
```

只有内容无法清楚放在 README 中时，才增加 `docs/INDEX.md`、`docs/product.md` 或 `docs/architecture.md`。

### Standard

适合多模块、有持久化数据、有领域术语、有部署需求或需要长期协作的软件：

```text
README.md
AGENTS.md
docs/INDEX.md
docs/product.md
docs/architecture.md
```

之后只按实际需要增加数据模型、术语、测试、运维、决策记录和长期计划。

### Advanced

只有普通文档、测试和 CI 无法解决具体问题时才使用。可能涉及：

- `.codex/config.toml`
- `.agents/skills/`
- `.codex/rules/`
- `.codex/hooks.json`
- `.codex/agents/`
- MCP 或 Connector
- 定时任务

选择 Advanced 不等于生成全部能力。每个高级表面必须有具体用例、数据边界、信任边界和停用方式。

## 自适应计划模块

Skill 不要求所有项目都建立严格的长期计划体系。只有发现长项目、跨会话继续、长期路线与当前功能并存、用户临时调整优先级，或 Codex 曾经选错计划时，才启用计划权限模块。

启用后由 Skill 自动建立清晰的职责：

| 文件 | 权限 |
| --- | --- |
| `docs/roadmap.md` | 长期方向，仅供参考，不授权执行 |
| `PLANS.md` | 当前唯一具有执行权的活动计划 |
| `docs/work/current.md` | 进度、证据和交接记录，不产生新任务 |
| `AGENTS.md` | 规定计划优先级、冲突处理和完成后的去向 |

普通用户只需要回答“现在最想先完善什么、完成后停下还是继续、哪些地方暂时不要碰”。Skill 负责把答案转换成活动计划、暂停任务、恢复条件和验证规则。

长期路线与当前功能冲突时，允许调整优先级，但不允许静默改变产品范围、架构、安全或数据兼容性边界。详见 [`references/planning-authority.md`](references/planning-authority.md)。

## 文件职责完整表

这些不是固定清单，而是信息归属表。项目只创建真正需要的文件。

| 文件或目录 | 负责什么 | 什么时候需要 |
| --- | --- | --- |
| `README.md` | 项目是什么、如何启动、文档入口 | 几乎所有项目 |
| `AGENTS.md` | Codex 的工作规则、验证要求 | 几乎所有项目 |
| `docs/INDEX.md` | 文档导航，告诉人和 Codex 去哪里找什么 | 文档超过两三个时 |
| `docs/product.md` | 用户、问题、流程、范围、非目标 | 产品型项目 |
| `docs/architecture.md` | 模块职责、依赖边界、数据流、技术选择 | 多模块或架构稍复杂时 |
| `docs/data-model.md` | 实体、字段含义、关系、不变量、敏感数据 | 有数据库或复杂业务对象时 |
| `docs/glossary.md` | 项目专有名词和准确含义 | 术语容易混淆时 |
| `docs/testing.md` | 测试层级、命令、测试数据、发布门槛 | 测试方式较复杂时 |
| `docs/operations.md` | 部署、配置、日志、监控、备份、恢复 | 需要上线或长期运行时 |
| `docs/decisions/` | 重要技术决策、替代方案和代价 | 有长期架构决策时 |
| `docs/roadmap.md` | 长期方向、里程碑和依赖关系，不授权执行 | 确实存在长期路线时 |
| `PLANS.md` | 当前唯一活动执行计划 | 多阶段、高风险、跨会话或计划容易混淆时 |
| `docs/work/current.md` | 当前进度和交接状态，不授权新任务 | 需要跨会话准确恢复时 |
| 子目录 `AGENTS.md` | 某个模块独有的规则 | 模块有不同命令、边界或风险时 |

高级能力默认不创建：

| 配置 | 用途 |
| --- | --- |
| `.codex/config.toml` | 项目专属 Codex 运行配置 |
| `.agents/skills/` | 项目内部反复使用的专用 Skill |
| `.codex/rules/` | 对特定命令允许、询问或禁止 |
| `.codex/hooks.json` | 在特定生命周期自动执行检查 |
| `.codex/agents/` | 自定义专业子 Agent |
| MCP / Connector | 连接 GitHub、Figma、数据库等外部系统 |
| Automation | 定时检查、监控和后续任务 |

## 推荐结构

```text
project/
├── README.md
├── AGENTS.md
├── docs/
│   ├── INDEX.md
│   ├── product.md
│   ├── architecture.md
│   ├── data-model.md       # 确实需要才有
│   ├── glossary.md         # 确实需要才有
│   ├── testing.md          # 确实需要才有
│   ├── operations.md       # 确实需要才有
│   ├── decisions/
│   ├── roadmap.md          # 有长期路线才有，仅供参考
│   └── work/
│       └── current.md      # 有跨会话进度才有
└── PLANS.md                # 有活动长计划才有
```

小项目可能只有：

```text
README.md
AGENTS.md
```

不要按文件夹数量创建 `AGENTS.md`。只有子目录具备不同的权威命令、架构边界、数据风险、团队归属或安全约束时，才创建嵌套文件。

## 安装

复制仓库到个人 Codex Skills 目录：

```text
%USERPROFILE%\.codex\skills\bootstrap-codex-project\
```

如果使用自定义 `CODEX_HOME`：

```text
%CODEX_HOME%\skills\bootstrap-codex-project\
```

安装后重新打开一个 Codex 任务，让 Skill 元数据重新加载。

## 使用方法

### 新项目

```text
使用 $bootstrap-codex-project。

我要开发一个本地资料管理软件：
- 用户是个人研究者
- 可以采集网页、PDF 和笔记
- 必须标明来源、可信状态和更新时间
- 使用 Tauri、React、SQLite
- 第一版不做云同步和多人协作

请在当前目录建立适合 Codex 长期开发的项目上下文。
```

### 现有仓库

```text
使用 $bootstrap-codex-project。

检查当前仓库，整理 README、docs 和 AGENTS.md。
以代码、配置和实际命令为准，删除重复、陈旧和无法验证的信息。
不要修改业务代码。
```

### 审计知识结构

```text
使用 $bootstrap-codex-project。

审计当前项目上下文，重点检查：
- 项目介绍和 AGENTS.md 是否混在一起
- 文档是否重复或互相矛盾
- 命令是否真实存在
- 哪些内容是已验证、已决定、计划中、临时假设或待确认
- 是否创建了不必要的嵌套 AGENTS.md
- 是否存在多余的 Skill、Hooks、Rules、MCP 或自定义 Agent
- 路线图、活动计划和进度记录是否混用了执行权限
- 是否存在多个看起来都能驱动 Codex 的活动计划
- 当前任务完成后是等待、恢复旧任务还是切换计划，是否写得明确

完成后直接修复。
```

### 长项目与临时优先级

```text
使用 $bootstrap-codex-project。

这是一个需要跨多个会话持续开发的项目。长期路线已经写在 docs/roadmap.md，
但我现在要优先完善“资料可信度标记”，暂时不要开发同步和推荐功能。
这个功能完成后先停下让我检查，再决定是否恢复长期路线。

请检查现有计划文件，建立清晰的执行权限、暂停任务、恢复条件、验收标准和交接记录。
不要修改业务代码。
```

用户不需要自己设计 `plan_id`、权限标记或文件结构。Skill 会先判断项目是否真的需要计划权限模块；如果不需要，就不会生成整套计划文件。

最简调用：

```text
使用 $bootstrap-codex-project，把当前项目整理成最小、准确、可信、适合 Codex 长期开发的上下文系统。
```

## 新会话是否重新调用

不需要每次调用。

- 项目整理好后，Codex 进入项目时会自动读取 `AGENTS.md`。
- 普通开发不必重新调用 Skill。
- README、架构、命令或目录明显变化时，再调用 Skill 审计或刷新。
- 新会话不会继承旧聊天内容，所以项目事实必须落在 README、docs、代码和测试中。
- 如果启用了计划权限模块，`AGENTS.md` 保存路由规则，`PLANS.md` 保存活动计划，`docs/work/current.md` 保存交接证据；新会话不应从路线图自行选择任务。
- 显式写 `$bootstrap-codex-project` 最可靠；符合描述时 Codex 也可能自动选择它。

刷新示例：

```text
使用 $bootstrap-codex-project，审计并更新当前项目上下文。
```

## 工作流程

1. 判断 Greenfield、Existing repository 或 Audit/refresh。
2. 对非空仓库运行只读检查器。
3. 从代码、manifest、测试和 CI 中提取事实，从用户或权威文档中提取意图与政策。
4. 只询问会改变架构、生成文件或安全边界的问题，每次不超过三个。
5. 选择 Minimal、Standard 或 Advanced，并独立判断是否启用计划权限模块。
6. 展示 Create、Update、Keep、Skip 四组文件计划。
7. 使用模板生成语义化文档并保留准确的人类内容。
8. 运行验证器，检查权威归属、计划权限、活动计划数量和完成去向。
9. 修复错误并解释保留的警告。

它不会自动：

- 虚构脚本、包管理器、目录或技术选型；
- 把产品介绍复制进 `AGENTS.md`；
- 为每个目录建立 Agent 文件；
- 生成没有实际用途的 MCP、Hooks、Rules、Plugins 或 Automations；
- 保存密码、Token 或其他凭据；
- 初始化 Git、提交、推送、部署或安装依赖，除非用户明确要求。

## 检查器和验证器

只读检查已有仓库：

```text
python "<skill-dir>\scripts\inspect_project.py" <project-root>
```

验证生成的上下文：

```text
python "<skill-dir>\scripts\validate_project_context.py" <project-root> --profile <minimal|standard|advanced>
```

验证器会检查：

- 档位要求的文件；
- 上下文 Markdown 的本地链接；
- 未替换的模板占位符；
- 常见密钥模式和个人绝对路径；
- npm、pnpm、yarn、bun 命令与 lockfile/package scripts 的冲突；
- 空泛的 Agent 规则；
- 多个包管理器造成的证据冲突；
- `AGENTS.override.md` 的遮蔽关系；
- 嵌套 `AGENTS.md` 是否复制根规则；
- 路线图、活动计划和进度记录是否声明了正确的执行权限；
- 是否存在多个同时具有排他执行权的活动计划；
- 活动计划的当前任务、允许范围、排除范围、验证和完成去向是否明确；
- 路线图中的复选框是否可能被误当成当前任务；
- 已加入的高级 Codex 表面。

验证通过不等于业务代码正确，也不能替代项目测试。

## 设计来源

本 Skill 的维护首先遵循 [`references/skill-design-principles.md`](references/skill-design-principles.md)：全面的是 Skill 的判断能力，不是它给每个项目生成的文件数量。用户入口保持白话和简单，复杂判断、证据分级、计划权限与安全降级由 Skill 内部完成。

本 Skill 借鉴但不复制以下项目：

- GitHub Spec Kit：区分需求、计划和实现；
- Caliber：先审计再写入，命令和路径必须有证据；
- AgentRules Architect：分析仓库事实，长任务使用持久计划；
- AGENTS.md Generator：根规则保持简洁，只创建必要的作用域规则；
- Project Bootstrapper：把结构、文档、测试和质量工具视为系统；
- TechWolf AI-First Toolkit：只问真正影响决策的问题。

Codex 表面名称和加载行为按官方文档校对，详见 [references/design-sources.md](references/design-sources.md)。

## 仓库内容

```text
SKILL.md
agents/openai.yaml
assets/templates/
references/
scripts/
tests/
docs/conversation-history.md
```

[对话背景与需求记录](docs/conversation-history.md) 保留本 Skill 形成过程中提出的批评、问题、设计要求和使用说明。

## 许可证

当前仓库没有附带许可证。GitHub 公开可见不等于自动授予再分发或修改权；正式开源时应由项目所有者明确选择 MIT、Apache-2.0 或其他许可证。
