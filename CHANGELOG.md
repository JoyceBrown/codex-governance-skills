# Changelog

## 0.1.1 - 2026-10-04

- 修复 Ubuntu/Linux 上组合示例被 artifact 校验器误判的跨平台路径问题，并改为按 schema 内容选择校验器。
- 将 `VERSION`/`CHANGELOG.md` 同步规则接入仓库门禁，提交和工作区检查都覆盖受保护的协议、验证器和 Skill 入口。
- 登记深度规划在体系外完成的边界，并保留有限的结论接收和需求澄清。
- 普通已授权代码修改直接走 TDD；未分类写入和高风险写入继续经过 Guard。
- 让 `artifact-v1` 把 `status` 留给各 Skill 定义，避免与 `composition-v1` 的分域状态混用。
- 为三堂会审增加轻量代码审查路由参考，外部独立审查能力保持可选。

## 0.1.0 - 2026-10-04

- 强制写入、外部副作用和重要完成声明经过 Guard 路由。
- PAO 事件接收增加项目计划、快照、commander 租约和 epoch fencing。
- wake 收据先登记后回调，活动通知 turn 保留并显式报告容量缺口。
- 安装器改用发布树复制，拒绝缓存、运行态文件和 Windows reparse point。
- 增加 artifact validator、术语表、ADR、边界说明和治理案例资产。

发布规则：修改 `SKILL.md`、协议 schema、验证器或宿主边界时先更新 `VERSION` 和本文件；未验证的真实宿主能力不得写成发布说明中的已支持能力。
