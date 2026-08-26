# 执行可靠性规则

规则是候选知识，不是全局 Hook。每条规则必须有以下字段，且只在相同触发条件和范围内适用：

`trigger`、`risk_level`、`wrong_pattern`、`correct_pattern`、`preflight`、`postcondition`、`retry_policy`、`source`、`scope`、`confidence`、`expiry_or_recheck`。

| trigger | 风险 | 正确动作 | 重试策略 |
| --- | --- | --- | --- |
| Windows 路径含空格、中文或括号 | medium | 使用 `-LiteralPath` 或参数数组；先确认解析后的绝对路径；中文本身不判错 | 解析失败先改参数，不重跑原字符串 |
| 路径过长、跨盘或目标不存在 | high | 先核验 `Resolve-Path`/`Path.GetFullPath`、长度和目标类型 | 目标未知时停止 |
| 环境变量只设置在上游 UI 进程 | high | 在实际启动构建器/脚本的同一进程设置并打印非敏感键名 | 先验证子进程可见性 |
| npm/pnpm、Node 或锁文件不匹配 | medium | 从项目声明和锁文件识别包管理器，确认版本和锁文件状态 | 不在换包管理器后直接重试 |
| 构建成功但包名、版本、appId 或 SHA256 不符 | high | 对最终产物做存在性、元数据和摘要核验 | 禁止把“构建成功”当完成 |
| 旧端口、watcher 或服务仍占用目标 | high | 识别 PID、命令行和所有权，确认是当前任务实例 | 所有权未知时停止，不杀进程 |
| Git 根、分支、worktree 或 nested repo 不明 | high | 读取 `git rev-parse`、当前提交和工作树状态 | 不在身份未确认时提交或发布 |
| UI 页面/浏览器状态可能过期 | medium | 重新观察当前页面和目标控件，再执行一次 | 过期状态不可直接重放点击 |
| 命令失败但状态未知 | high | 检查结果文件、锁、进程、产物和日志摘要 | 不自动重试 |
| 同一动作第一次明确失败 | low/medium | 只有目标指纹、参数和权限未变且失败原因可重试时允许一次 | 第二次失败后转诊断或询问 |

规则生命周期：`Candidate -> Shadow -> Active`。一次偶然失败只能形成 `Candidate`；至少有可复现证据、成功后置条件和适用范围，且经过一次独立复核，才可进入 `Active`。规则过期或环境变化时回到 `Shadow`，不得把 Skill 自身变成永久错误记忆。
