---
name: tdd-loop
description: 在用户授权的代码变更中，用有界的测试先行、实现、回归和用户路径验证闭环交付；不把单个测试通过误报为功能完成。
---

# TDD Loop

测试驱动是反馈回路，不是强迫每行代码先写测试的仪式。选择能区分失败行为且成本合理的测试层级。

## 回路

1. 记录原始复现、目标行为、范围和不应改变的行为。
2. 写一个最小失败测试或可重复检查，确认它确实能失败。
3. 做最小实现，保持接口和权限边界不变。
4. 运行目标测试，再运行受影响的回归集合。
5. 用真实用户路径或安装后行为验证，不把静态检查当成端到端证据。
6. 对照需求逐项检查遗漏、临时绕过、性能成本和回滚方式。

## 输出

保留 `red`、`green`、`refactor`、测试命令、环境、结果、未覆盖项和下一步。测试失败时保留证据；没有真实用户路径验证时状态只能是 `PARTIAL`。

## Output Contract

每轮测试闭环返回稳定收据；本地通过和真实用户路径结果分开记录：

```json
{
  "action_status": "READY | PARTIAL | BLOCKED",
  "execution_status": "IN_PROGRESS | COMPLETED | FAILED | UNKNOWN",
  "review_status": "PASS | ISSUE | OPEN",
  "red": "失败测试或 null",
  "green": "实现与目标测试或 null",
  "refactor": "重构结果或 null",
  "test_evidence": [],
  "user_path_result": "VERIFIED | PARTIAL | UNKNOWN",
  "evidence_refs": [],
  "next_action": "一个最小动作或 null",
  "budget": {"chars": 0, "calls": 0}
}
```

`execution_status=COMPLETED` 不能掩盖 `user_path_result=UNKNOWN`；这时最多将整体结果报告为 `PARTIAL`。

## 边界

只修改用户授权范围。不得自动提交、推送、部署、迁移、删除或安装陌生依赖。Guard 的事实门禁、回滚要求和完成收据优先于本 Skill 的便利性。

## 组合与独立运行合同

遵循 `composition-v1`（见 `docs/composition.md`）。单独使用时在授权范围内完成有界的测试先行、实现、回归和用户路径验证；缺少协作者不阻塞本地闭环，但未验证的外部结果必须保持 `UNKNOWN` 或 `PARTIAL`。

- 可选借用 `diagnose` 的区分性检查、`execution-reliability` 的目标身份和产物证据、Guard 的授权/完成门禁或 `architecture-health` 的边界发现；这些输入不能扩大代码范围。
- 对外返回 `action_status`、`execution_status`、`review_status`、`evidence_refs`、`next_action` 和 `budget`。组合失败时回退到本地测试流程；不能用 `COMPLETED` 掩盖用户路径或外部副作用未验证。

