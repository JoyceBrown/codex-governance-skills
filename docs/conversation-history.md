# 对话背景与需求记录

本文保留本 Skill 形成过程中可见的需求原文、问题脉络和已经给出的解答。它不是运行时规则；运行时以 `SKILL.md`、`references/`、`assets/templates/` 和 `scripts/` 为准。

## 一、问题起点

用户：

> http://127.0.0.1:4180/ 从排版/交互/易用性/美观等客户角度出发，分析这个网站，然后给出修改建议，包括其现存的缺陷以及细节毛病。要做到吹毛求疵

用户：

> 继续

用户：

> 最重要的一点，作为资料管理器，页面毫无逻辑，排版混乱；作为知识库，层级乱七八糟，信息也不明确，我甚至不知道，哪些可用，哪些不可信。采集来源谁看的懂？

用户：

> 这个应用是不是脱裤子放屁？好像没什么实际用处

用户：

> 什么才是最适合codex知识库的最佳形态？有必要做这个知识库吗？

用户：

> 面对一个长项目，如何减少上下文过长导致的codex的token消耗

这些问题把方向从“做一个资料管理器”转向“建立清晰的项目上下文系统”：项目事实、Codex 工作约束和可选能力必须分开，来源与可信状态必须明确，而且不能为了管理上下文再制造一套混乱的知识库。

## 二、关于 AGENTS.md、项目介绍和上下文分工

用户：

> 如何正确使用agent.md？比如我开发一个软件，这个软件用到了很多文件夹，每个文件夹都要新建一个agent.md文件吗？请用最白的语言解惑

用户：

> agents.md是项目约束   那项目介绍放在哪？

用户：

> 除了这些还有吗？从Agents.md如何使用开始，扩展到其他的，把所有涉及的都结构完整地把这些都列出来。

形成的核心分工是：

- `README.md`：项目介绍、入口、安装和运行方式；
- `AGENTS.md`：Codex 的工作约束、验证要求和阅读路由；
- `docs/product.md`：产品问题、用户、范围、流程和非目标；
- `docs/architecture.md`：模块边界、依赖关系、数据流和技术选择；
- 其他 `docs/` 文件只在对应信息确实复杂时创建；
- 子目录只有在存在不同命令、边界、风险或团队规则时才建立嵌套 `AGENTS.md`。

## 三、关于是否需要这个 Skill

用户：

> 有没有这样一个技能，我输入一个项目介绍，例如我想做一个什么什么项目或软件，然后这个技能自动帮我写好这些规则配置？

用户：

> github上有现成开源技能做到这个的吗？

用户：

> 可以从网络寻找，不只是在github仓库里找。

结论是：可以做一个 Skill，但它不应是“把所有 AI 配置一次性生成”的脚手架，而应是一个根据项目证据选择最小上下文系统的工作流。

设计时参考了 GitHub Spec Kit、Caliber、AgentRules Architect、AGENTS.md Generator、Project Bootstrapper 和 TechWolf AI-First Toolkit，并保留其有价值的思想，去掉强制仪式、平台特定路径、远程治理和无用配置。

## 四、Skill 初版完成后的说明

Skill 名称：`bootstrap-codex-project`。

原始个人安装位置：

```text
C:\Users\JIE\.codex\skills\bootstrap-codex-project
```

它包含三层语义：

1. 项目事实：`README.md`、`docs/`、代码、测试和决策记录；
2. Codex 指导：根或必要的嵌套 `AGENTS.md`；
3. 可选能力：`.codex/`、`.agents/skills/`、MCP、Rules、Hooks、自定义 Agent 和定时任务。

它支持 Greenfield、Existing repository、Audit/refresh 三种模式，以及 Minimal、Standard、Advanced 三档输出。高级表面从不因为“完整”而自动生成。

完成过的验证包括：

- 官方 `quick_validate.py`；
- 两个 Python 脚本语法检查；
- 仓库检查器和上下文验证器的正向、负向测试；
- 本地链接、占位符、个人路径、密钥模式、嵌套规则和高级表面检查。

## 五、如何使用

用户：

> 怎么用？

给出的使用方式：

```text
使用 $bootstrap-codex-project。

我要开发一个……
```

现有项目审计示例：

```text
使用 $bootstrap-codex-project，审计当前仓库的 README、docs 和 AGENTS.md，
删除重复和不可信内容，整理成最小但完整的 Codex 项目上下文。
```

## 六、新会话是否需要重新调用

用户：

> 换新会话需要重新调用skill吗？

结论：不需要每次都调用。

- 项目已经整理好后，新会话进入项目时会自动读取项目里的 `AGENTS.md`；
- 普通开发不必重新调用 Skill；
- README、架构、命令或目录明显变化时，再调用 Skill 做审计或刷新；
- 新会话不会继承旧聊天内容，所以事实必须保存在项目文件中；
- 显式写 `$bootstrap-codex-project` 最可靠，也可以让 Codex 根据描述自动匹配。

## 七、完整文件体系

用户：

> 只有这几个吗？README.md：项目介绍、入口和运行方式 AGENTS.md：Codex 工作约束 docs/product.md：产品范围 docs/architecture.md：架构边界

不是只有这几个。它们是核心文件，不是固定清单。

| 文件或目录 | 负责什么 | 什么时候需要 |
| --- | --- | --- |
| `README.md` | 项目是什么、如何启动、文档入口 | 几乎所有项目 |
| `AGENTS.md` | Codex 的工作规则、验证要求 | 几乎所有项目 |
| `docs/INDEX.md` | 文档导航 | 文档超过两三个时 |
| `docs/product.md` | 用户、问题、流程、范围、非目标 | 产品型项目 |
| `docs/architecture.md` | 模块职责、依赖边界、数据流、技术选择 | 多模块项目 |
| `docs/data-model.md` | 实体、关系、不变量、敏感数据 | 有数据库或复杂业务对象时 |
| `docs/glossary.md` | 专有名词和准确含义 | 术语容易混淆时 |
| `docs/testing.md` | 测试层级和发布门槛 | 测试方式较复杂时 |
| `docs/operations.md` | 部署、配置、监控、备份和恢复 | 长期运行或上线时 |
| `docs/decisions/` | 长期技术决策和替代方案 | 有重要架构决策时 |
| `docs/work/current.md` | 当前进度和临时问题 | 长项目跨会话工作时 |
| `PLANS.md` | 多阶段任务计划契约 | 高风险长任务 |
| 子目录 `AGENTS.md` | 局部规则 | 子目录有真实差异时 |

高级能力包括 `.codex/config.toml`、`.agents/skills/`、`.codex/rules/`、`.codex/hooks.json`、`.codex/agents/`、MCP 和 Automation，但都不是默认必需品。

## 八、当前公开发布请求

用户：

> 将技能上传我的github并公开仓库，附上用途（详细版）和使用说明，以及包括上面这段对话提到的内容，不要删减

本仓库就是对此请求的发布包：它保留 Skill 原文件、详细用途、完整使用说明、文件职责、证据状态、设计来源，以及本文件之前的可见需求与结论。
