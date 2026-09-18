# HCR 6.2 接回说明

这次接回把 `human-centered-reasoning-v6.2.0.zip` 作为用户提供的参考输入，
将经修复的能力增量放回合集现有的
`skills/human-centered-reasoning-guard`。长期维护权威仍是
`codex-governance-skills` 的 `main` 分支和该目录；压缩包的 `dist/`、覆盖式
安装脚本和任何平行顶层入口都不参与安装或发现。讨论文档是架构参考，不是
额外要求来源。

## 保留的原边界

Guard 仍是唯一入口和治理门禁。Fact/Goal gate、目标身份、漂移、回滚、完成
验证、Memory Policy、Durable Ledger 以及 Active User-Perspective Mode 继续由
原 Guard 负责。`intent-alignment`、`diagnose`、`tdd-loop`、`durable-context`
和其他合集技能只通过原有的有限信封交换证据引用和下一步，不会被 HCR Replay
调用来取得权限。

HCR 的 WHY/WHAT/HOW、认识论状态、结构推理和 Cognitive Replay 是 Guard 内的
可选认知模式。WHY 取当前用户意图，WHAT 取当前需求与可见验收，HOW 只是批准
范围内的候选路线。认知标签与合集治理状态分开：`FACT` 需要来源、范围、证据
和验证时间；`governance_status` 只是现有 owner 的只读投影。HCR 不能改
Project Truth、`PLANS.md`、Requirement Ledger、Runtime、权限或完成状态。

## 已修复的归档缺陷

- Replay 现在要求项目、环境、Runtime、依赖、有效期、证据和当前 constraints
  可核对；`superseded`、`retired`、过期、无证据或父链不完整的记录不能成为
  候选。constraints 使用与记录的适用集合完全匹配。
- 输入拒绝非有限数、布尔伪数字、未知字段、重复/悬空/循环节点、非法时间、
  超长字段、重复引用、超大 JSON、过深图和路径爆炸。CLI 对缺失文件、畸形
  JSON、重复键和预算错误只返回有界错误，不打印 traceback。
- Schema 校验器只解析随 Guard 发布的本地 schema 和本地 `$ref`，拒绝外部
  引用、未知关键字、不支持的格式、重复键和非有限常量；Replay 结果固定为
  `llm_calls=0`、`execution_authorized=false`、`current_truth_established=false`。
- 路径显式报告终点进度、累计成本、提前停止和深度截断；没有适用历史时返回
  `NO_APPLICABLE_EXPERIENCE`，回到当前证据或结构推理。

## 接口与写回

`replay/evaluator.py` 是零 LLM、只读、确定性的适配器。它只接受已经授权的
ExperienceNode 投影；原 Guard 的 `observations.jsonl` 缺少 WHY/WHAT、结果、
进度或适用性时必须省略，不能猜测补齐。候选分数是搜索 utility，不是事实
概率、批准或执行指令。结果只能提出 `VERIFY_CANDIDATE` 或
`REASON_OR_COLLECT_EVIDENCE`。

Experience、需求和 Epistemic 记录都回到各自现有 owner 的生命周期；本次接回
不创建第二个账本、Memory Authority、数据库、Hook、Runtime 或后台服务。写回
必须是经脱敏的候选/观察，是否追加、审查、晋升由原 owner 和既有授权决定。

## 验证证据

离线包验证会检查唯一 `SKILL.md`、本地资源、Python 语法、8 个 bundled schema
以及示例 Replay。仓库验证还运行 Guard Python 测试、原 PowerShell 回归、合集
合同测试、安装 Smoke Test 和可用时的 `quick_validate.py`。这些证据证明源码
和本地工具契约一致；没有安装到当前 Codex 运行时，也没有进行真实用户/设备
路径验收，因此不能据此宣称实际用户收益或生产生效。
