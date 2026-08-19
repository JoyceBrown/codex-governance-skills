# Bootstrap Codex Project

把一个项目想法或已有仓库，整理成最小、准确、可信、可维护、适合 Codex 长期工作的项目上下文系统。

这个仓库包含一个可安装的 Codex Skill。它不会把项目变成臃肿的“AI 配置包”，也不会为了看起来完整而给每个文件夹生成 `AGENTS.md`。它解决九个问题：

1. 这个项目到底要解决什么问题？
2. 哪些内容已经验证，哪些只是决定、计划、假设或待确认？
3. Codex 修改项目时必须遵守什么规则？
4. 当前任务应该读取哪些文件，而不是把整个仓库塞入上下文？
5. 个人开发者如何从真实问题压缩出 MVP、首条垂直切片和可发布门槛？
6. 项目中途新增要求，到底是当前任务调整、临时插队，还是改变长期方向？
7. 开新任务或子代理后，哪些规则会跟随，哪些上下文必须明确交接？
8. 做过更多项目后，怎样吸收真实经验，同时避免把单个项目的特殊情况污染所有新项目？
9. 长任务中怎样正确理解“继续”、防止局部完成、重复死磕、工具误判和交付不闭环？

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

## 怎样让 Skill 越用越聪明

真正可靠的“学习”不是让模型随意记住聊天，也不是每次被用户纠正后就往 `SKILL.md` 追加一句规则。这样做很快会产生互相冲突、只适合某个项目、无法验证的提示词垃圾。

本 Skill 使用三层学习结构：

| 层级 | 负责什么 | 能否直接约束项目 |
| --- | --- | --- |
| Codex Memories | 帮助回忆用户偏好、近期工作和重复背景 | 不能作为必须执行规则的唯一来源 |
| 私有经验注册表 | 自动保存脱敏证据、影子验证、局部启用、隔离冲突和回滚 | Shadow 仅用于验证；Active 匹配当前项目时可作为建议 |
| 版本化 Skill | 保存已经泛化、验证并有回归测试的通用能力 | 可以按 Skill 路由规则稳定执行 |

项目自身的硬规则仍然必须写入项目的 `AGENTS.md`、docs、代码、测试或活动计划。即使个人经验库丢失，项目也不能因此失去关键约束。

### 一条经验如何成长

```text
真实问题或用户纠正
    -> 脱敏候选 candidate
    -> 两个独立项目，或严重问题复现 -> shadow
    -> 在匹配的新项目中仅作验证建议
    -> 两个独立的实际收益 -> active
    -> 冲突自动隔离 / 回归自动撤回
    -> 前向测试 + 反例 + 回归测试
    -> 用户授权后更新 Skill
    -> promoted
```

`candidate` 不影响其他项目；`shadow` 只能提示验证方法；`active` 才能在类型、范围、风险信号和当前仓库证据都匹配时作为建议。`conflicted` 与 `rolled_back` 自动停止使用。已经进入 Skill 的 `promoted` 经验不会再次注入上下文，避免重复。

### 哪些自动，哪些仍需授权

不同项目经常给出相反答案：

- 桌面本地工具可能应该使用 SQLite，云服务可能应该使用 PostgreSQL；
- 个人原型可以简化权限系统，企业系统不可以；
- 某个项目需要严格计划权限，小项目可能只需要 README 和一个 `AGENTS.md`；
- 用户的一次个人偏好，不等于所有用户和所有项目的最佳实践。

因此私有注册表会自动发现、脱敏、去重、审核证据、进入 Shadow、晋升 Active、隔离冲突和回滚退化，不需要用户逐条管理。只有把经验写入版本化 Skill、提交或推送这一层需要一次明确授权；私有经验不会暗中改写正式规则。

### 私有经验存放位置

默认位置：

```text
%CODEX_HOME%\learning\bootstrap-codex-project\
```

未设置 `CODEX_HOME` 时使用个人 Codex 目录。这里保存的是本机私有生成状态，不会提交到公开仓库，也不保存原始聊天、源代码、客户名称、仓库路径、密钥或长日志。

工具会实际执行模式边界：`off` 拒绝写入；`ask` 必须在用户本次同意后传入 `--confirm-capture`；`auto_sanitized` 才能自动登记候选。记录采用结构校验、原子替换，并在操作系统支持时使用私有文件权限。自动脱敏能识别常见令牌、带凭据 URL、密钥赋值、私钥块、邮箱和用户目录，但无法可靠识别所有客户名或业务敏感信息，因此只能登记概括后的结构化摘要，不能把原始材料交给脱敏器碰碰运气。

查看当前记录模式：

```text
python "<skill-dir>\scripts\experience_registry.py" config
```

三种模式：

| 模式 | 行为 |
| --- | --- |
| `off` | 不发现、不保存经验候选 |
| `ask` | 发现真实可复用问题后先询问用户 |
| `auto_sanitized` | 默认模式；识别到真实摩擦时自动保存并审核私有生命周期，但不修改或发布正式 Skill |

切换为自动保存脱敏候选：

```text
python "<skill-dir>\scripts\experience_registry.py" configure --capture-mode auto_sanitized
```

通常由 Skill 自动操作，任务结束时运行 `finalize` 并留下私有回执；没有合格经验时也会记录 `no-eligible-experience`。用户无需逐条管理：

```text
# 任务结束时自动审核、迁移并写入回执
python "<skill-dir>\scripts\experience_registry.py" finalize --run-summary "本次任务的脱敏摘要"

# 记录 Shadow 在独立项目中的实际收益；第二个独立收益会自动晋升 Active
python "<skill-dir>\scripts\experience_registry.py" observe EXP-20260726-1234abcd --kind shadow-benefit --summary "验证发现并避免了重复权威" --project-root <project-root>

# 检查它是否具备进入 Skill 的基础证据
python "<skill-dir>\scripts\experience_registry.py" assess EXP-20260726-1234abcd

# 完成修改与测试后登记晋升；仅在当前用户明确批准时使用 --user-approved
python "<skill-dir>\scripts\experience_registry.py" mark-promoted EXP-20260726-1234abcd --target SKILL.md --forward-test "representative fixture passed" --regression-test "unit suite passed" --approval-note "用户批准将该通用规则更新到 Skill" --user-approved
```

`assess` 只检查机械门槛，不会修改 Skill，也不会替用户批准发布。

若新候选针对同一问题和适用范围提出不同做法，工具会列出 `conflicts_with` 并自动隔离已经可复用的冲突项，不会按“较新”自动覆盖。无法靠证据确定时，它留在隔离区并批量报告；已经晋升进版本化 Skill 的经验绝不能在私有库里覆盖。

详细规则见 [`references/experience-learning.md`](references/experience-learning.md)。

经验查询和采集发生在调用本 Skill 的任务中；它不是后台监控器，也不会观察未调用该 Skill 的所有开发会话。

## 三种模式

### Greenfield

用户提供项目想法，目标目录为空或尚未创建。Skill 提炼目标用户、问题、首条完整工作流、范围、非目标、技术方向和未决问题。

### Existing repository

项目已有代码或配置。Skill 先只读检查 README、`AGENTS.md`、manifest、包管理器、测试、CI 和文档，再决定需要创建或修改什么。

### Audit or refresh

用于修复过期命令、重复文档、规则覆盖、来源不明、说明与代码矛盾，以及没有真实用途的高级配置。

## 个人软件交付生命周期

当用户正在规划首版、判断里程碑能否推进、比较复用与自研、准备发布，或决定继续、简化、转向或停止时，Skill 按需加载 [`references/solo-software-delivery.md`](references/solo-software-delivery.md)。

该模块把独立开发流程压缩为八个证据门槛：现实约束、问题证据、首版价值闭环、技术侦察、最简单架构与首条垂直切片、有限开发循环、发布就绪和反馈决策。它不会要求每个门槛生成一份文件，也不会因为门槛通过就自动获得提交、推送、部署、迁移或发布权限。

普通 Bug 修复、代码解释或边界清楚的单次实现不会被强制套用完整生命周期。产品事实写入现有 `docs/product.md`，技术结论进入架构或决策记录，发布要求进入测试与运维文档；只有长周期、跨会话或计划冲突工作才启用 `PLANS.md`。

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

## 长任务执行纪律

当项目出现长时间自主开发、用户反复说“继续”、多个要求必须一起完成、失败方法反复重试、发布产物或用户可见状态等信号时，Skill 会启用
[`references/execution-discipline.md`](references/execution-discipline.md)。

它包含十条由真实项目错误晋升而来的规则：

1. “继续”先验收当前任务，未完成则补齐，已完成才进入下一个已授权里程碑。
2. 用户明确绑定的多项要求是一个完成单位，局部结果只能算进度。
3. 用户可见结果优先于无直接收益的内部兴趣点，除非内部工作是已证明的安全或架构前置条件。
4. 重要用户决定进入产品、架构、决策、计划或检查点的唯一权威所有者。
5. 声称终端、编辑器、Git、依赖、权限或运行能力缺失前，必须检查当前环境并提供证据。
6. 失败方法没有新证据或条件变化时不能原样重试，必须记录失败并改变假设或策略。
7. 交付产物时主动报告版本、位置、身份、验证、工作树、提交、推送或发布状态及已知限制。
8. 会改变解决方案的领域术语先统一含义，再进入术语表或领域文档。
9. 用户功能以实际生效、等待、失败和下一步操作等可见状态验收，不能只证明后台代码存在。
10. 共享 UI、配置、数据或 API 变更按真实影响范围验证代表性页面、尺寸、调用者或兼容边界。

这些规则不改变原有权限模型：“继续”不能选择未授权路线图任务，用户价值不能越过安全与明确排除范围，能力检查不能扩大副作用权限，交付报告也不自动授权提交、推送、发布或部署。短任务和没有对应风险信号的项目不会被强制套用完整执行纪律。

## 中途提出新要求时会怎样

用户不需要说“这是短期支线”或“这是路线图变更”。Skill 根据真实影响自动分为三类：

| 内部分组 | 白话含义 | Skill 怎么处理 |
| --- | --- | --- |
| `task_adjustment` | 还是当前这件事，只是改做法或验收细节 | 更新当前任务和验收条件，不碰长期路线 |
| `priority_branch` | 先做另一件事，之后再停下或回来 | 更新活动计划，保留暂停项、原因、影响、恢复条件和完成去向 |
| `roadmap_change` | 项目的长期目标或重要边界变了 | 先更新产品、架构或决策文档，再调整活动计划 |

Skill 会先判断，只有在不同答案会改变长期边界或“做完后回不回来”时才问一句白话问题。例如：

```text
“先把导出做完，再继续登录”
```

通常是临时优先支线。

```text
“以后取消云同步，产品只做本地版”
```

属于长期方向变更，不能伪装成普通插队。

```text
“顺便优化设置页”
```

如果无法判断它属于当前任务还是新优先项，Skill 会问用户，而不是擅自扩大范围。完整规则见 [`references/change-intake-and-agent-handoff.md`](references/change-intake-and-agent-handoff.md)。

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

从 `codex-governance-skills` 合集根目录运行安装器：

```powershell
.\scripts\install.ps1 -Names bootstrap-codex-project
```

如果需要安装到自定义技能根目录：

```powershell
.\scripts\install.ps1 -Names bootstrap-codex-project -TargetSkillsRoot 'E:\path\to\.codex\skills'
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

### 个人 MVP 与发布判断

```text
使用 $bootstrap-codex-project。

我要一个人开发面向设计师的本地素材整理工具。请先根据已有证据和现实约束，
压缩首版核心价值闭环，比较可复用方案与自研边界，选择第一条垂直切片，
并给出进入开发前的产品、工程和运维门槛。不要先写代码，也不要默认生成全套文档。
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

### 让 Skill 记住一次教训

普通用户可以直接说：

```text
使用 $bootstrap-codex-project。

复盘这次项目整理过程。把真正可复用的问题整理成脱敏经验候选，
项目特有要求留在当前项目，不要直接修改 Skill。
```

Skill 会提炼“发生了什么、为什么错、以后什么情况下应该怎样做”，并根据当前记录模式询问后保存，或自动保存为候选。它不会复制整段对话。

### 审查已经积累的经验

```text
使用 $bootstrap-codex-project。

审查本地积累的经验候选：
- 合并重复项
- 区分当前项目、同类项目和跨项目经验
- 拒绝没有证据或过度泛化的内容
- 告诉我哪些可以批准为本地经验
```

### 把成熟经验升级到 Skill

```text
使用 $bootstrap-codex-project。

检查本地已批准经验中，哪些已经在多个独立项目出现，
或属于已复现的严重问题。只对通过泛化、反例、前向测试和
回归测试的经验更新 Skill。先说明修改位置，得到我的授权后
再同步安装副本和发布 GitHub。
```

适合所有运行都需要的核心判断进入 `SKILL.md`；只适合某类项目的条件经验进入 `references/`；机械识别问题进入脚本和测试；只适合一个项目的经验永远留在该项目。

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

### 新任务、分叉和子代理的区别

| 情况 | 会自动带上什么 | 不会可靠带上什么 | 正确做法 |
| --- | --- | --- | --- |
| 新任务或 `/new` | 在正确仓库、工作树和目录中，适用的 `AGENTS.md` 会重新发现 | 旧聊天原文、未写入仓库的临时决定 | 从 `PLANS.md` 和 `docs/work/current.md` 恢复，并显式传递仓库状态和责任归属 |
| `/fork` | 分叉点之前的聊天上下文 | 分叉后另一边的新决定和新进度 | 重要变化仍写回权威项目文件 |
| 主代理新建子代理 | 可访问的仓库和持久规则 | 当前目标、最新要求、排除范围、验收标准不会自动完整理解 | 主代理发送边界明确的任务包，并负责最终集成和验收 |

所以不能笼统地说“所有规则都会自动跟随”。真正会稳定跟随的是正确作用域中的持久规则；更近目录的 `AGENTS.md` 或 `AGENTS.override.md` 还可能改变最终生效规则。当前任务的具体意图必须进入活动计划、交接记录或主代理发送的任务包。

另一个 Codex 任务要正式继续或接管时，还要传递工作树、分支、基准提交、未提交改动、并发任务与重叠编辑范围、已失败尝试与策略变化、当前目标、验收条件、最新用户决定、下一动作、外部副作用权限，以及它是“协助”“继续”还是“正式接管”。正式接管后，新任务负责集成和本次用户请求的最终汇报；“整个项目完成”仍需要单独的项目级验收标准。模板见 [`assets/templates/new-task-handoff.md`](assets/templates/new-task-handoff.md)。

子代理任务包至少包含：

```text
task_id
objective
requirement_change_class
allowed_scope
excluded_scope
authoritative_files
acceptance_criteria
validation
write_policy
repository_state
side_effects_policy
escalation
expected_return
```

`side_effects_policy` 用来明确是否允许安装依赖、联网、修改外部系统或数据库、提交、推送、部署和破坏性操作；未明确允许的外部或破坏性副作用默认禁止。如果任务包与用户指令、适用的 `AGENTS.md` 或 `PLANS.md` 冲突，子代理必须停止并报告，不能自行扩大解释。

默认情况下，子代理只能完成这个有限任务，不能自行修改长期路线、改变活动计划权限、扩大范围、挑选其他路线图任务，或宣布整个项目已经完成。普通用户不需要手填这些内部字段，由 Skill 或主代理根据仓库事实生成。模板见 [`assets/templates/agent-task-packet.md`](assets/templates/agent-task-packet.md)。

刷新示例：

```text
使用 $bootstrap-codex-project，审计并更新当前项目上下文。
```

## 工作流程

1. 判断 Greenfield、Existing repository 或 Audit/refresh。
2. 对非空仓库运行只读检查器。
3. 从代码、manifest、测试和 CI 中提取事实，从用户或权威文档中提取意图与政策。
4. 只询问会改变架构、生成文件或安全边界的问题，每次不超过三个。
5. 选择 Minimal、Standard 或 Advanced，并独立判断是否启用个人软件交付、计划权限等可选模块。
6. 个人软件交付信号存在时，建立问题证据、首版价值闭环、技术侦察、垂直切片、发布和反馈门槛。
7. 查询与当前项目类型和风险信号匹配的已批准本地经验；候选经验不参与决策。
8. 展示 Create、Update、Keep、Skip 四组文件计划。
9. 使用模板生成语义化文档并保留准确的人类内容。
10. 运行验证器，检查权威归属、计划权限、活动计划数量和完成去向。
11. 中途需求发生变化时，判断它影响当前任务、临时优先级还是长期方向，并更新对应的权威文件。
12. 需要跨任务或委派时，建立可恢复的交接状态和有限任务包。
13. 真实摩擦产生可复用教训时，按记录模式形成脱敏候选。
14. 长任务出现匹配信号时，应用执行纪律，记录完成边界、尝试变化、交付状态和用户可见验收。
15. 修复错误并解释保留的警告。

它不会自动：

- 虚构脚本、包管理器、目录或技术选型；
- 把产品介绍复制进 `AGENTS.md`；
- 为每个目录建立 Agent 文件；
- 生成没有实际用途的 MCP、Hooks、Rules、Plugins 或 Automations；
- 保存密码、Token 或其他凭据；
- 把 Codex Memories、未审查候选或另一个项目的特殊规则当成当前项目事实；
- 保存原始聊天、源代码、客户信息、个人路径或长日志到经验库；
- 因为一条候选经验自动修改 Skill、提交或推送；
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
- 带版本号或非标准命名的路线图、计划、当前工作和交接文件是否被识别；
- 是否存在多个同时具有排他执行权的活动计划；
- 活动计划的当前任务、允许范围、排除范围、验证和完成去向是否明确；
- 活动计划是否声明 validate-then-advance、全部必需项完成、优先级依据和交付契约；
- 同一规划字段是否出现冲突值，且是否只有一个与 `current_task_id` 一致的 `in_progress` 里程碑；
- 活动计划是否记录了最新需求变更的 ID、分类和正确的长期权威引用；
- 临时优先支线是否记录暂停工作、原因、影响和恢复条件；
- `AGENTS.md` 是否包含需求分类路由和子代理权限边界；
- 路线图中的复选框是否可能被误当成当前任务；
- 永久项目文档是否硬编码当前仓库的本机绝对路径；
- 已加入的高级 Codex 表面、配置语法，以及必须另行人工检查的权限、副作用和信任边界；
- Python、Cargo、Go、Make、Maven、Gradle、.NET 等无法由验证器机械证明的命令声明。

验证通过不等于业务代码正确，也不能替代项目测试。警告中的命令与高级表面必须保留为未验证事项，不能因为 `ok: true` 就声称已经证实。检查器若返回 `scan.complete: false`，必须提高 `--max-files` 或定向读取相关文件后再判断某项内容不存在。

经验库工具：

```text
python "<skill-dir>\scripts\experience_registry.py" --help
```

它负责脱敏、去重、独立项目计数、适用范围过滤、人工审查状态和晋升门槛检查。晋升门槛检查只是证据提示，不能代替用户授权和真实测试。

## 设计来源

本 Skill 的维护首先遵循 [`references/skill-design-principles.md`](references/skill-design-principles.md)：全面的是 Skill 的判断能力，不是它给每个项目生成的文件数量。用户入口保持白话和简单，复杂判断、证据分级、计划权限与安全降级由 Skill 内部完成。

本 Skill 借鉴但不复制以下项目：

- GitHub Spec Kit：区分需求、计划和实现；
- Caliber：先审计再写入，命令和路径必须有证据；
- AgentRules Architect：分析仓库事实，长任务使用持久计划；
- AGENTS.md Generator：根规则保持简洁，只创建必要的作用域规则；
- Project Bootstrapper：把结构、文档、测试和质量工具视为系统；
- TechWolf AI-First Toolkit：只问真正影响决策的问题。

Codex 表面名称、加载行为和 Memories 边界按官方文档校对，详见 [references/design-sources.md](references/design-sources.md)。

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
