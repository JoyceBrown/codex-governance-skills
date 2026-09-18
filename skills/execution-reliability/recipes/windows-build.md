# Windows 构建配方

适用于桌面端或 Electron 构建：

1. 识别源码根、包管理器、Node 版本和锁文件。
2. 确认构建输出目录和目标平台，清楚区分 Electron 构建与 electron-builder 打包。
3. 先确认产品变体。Candidate、staging、release 等命名变体必须使用项目专用包装器或显式 `--flavor`；没有身份参数的通用 `package:win` 不能进入执行阶段。若包装器提供 `--check`，先运行检查模式并确认身份，再启动 `electron-builder`。
4. 在实际启动打包器的同一进程设置变量，保留非敏感键名收据。
5. 构建完成后运行 `verify-artifact.py`，核对名称、版本、元数据和摘要；同时检查 effective config 的 `appId`、`productName`、`artifactName` 和输出目录。
6. 安装或替换前由 Guard 确认授权、回滚点和当前运行实例。

遇到路径或变量问题，不先删除缓存或整包重建；先运行最小预检，改变明确的输入后再执行一次。
