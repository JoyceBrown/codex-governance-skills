---
name: diagnose
description: 诊断软件、自动化或工作流中的失败和不一致；建立竞争根因、最小复现、区分性检查和证据链，避免症状修补和重复尝试。
---

# Diagnose

诊断的产物是更可靠的根因判断和下一项检查，不是凭感觉给出补丁。

## 工作方式

1. 写出用户可见的症状、发生路径、频率、版本和真实成本。
2. 至少提出两个互相竞争的解释，分别写出预测和最便宜的反证检查。
3. 从用户路径向后追踪数据、状态、缓存、传输、权限和环境边界。
4. 运行一次区分性检查，再决定继续诊断、修复、回滚、询问或停止。
5. 记录 `observed`、`inferred`、`unknown` 和 `reproduction`，不要把模型猜测写成事实。

## 输出

```text
symptom / reproduction
hypotheses: 至少两项
discriminating_check / result
root_cause: CONFIRMED | LIKELY | OPEN | CONFLICTED
user_impact
next_action / budget
```

默认只读。用户明确授权实现时，交给 TDD Loop 或项目原有工程流程；同一假设连续失败两次后切换假设，不重复原命令。

## 组合与独立运行合同

遵循 `composition-v1`（见 `docs/composition.md`）。单独使用时至少保留两个竞争假设、一次区分性检查和一个最小下一动作；没有执行证据时保持 `OPEN` 或 `CONFLICTED`，不自动修复。

- 可选借用 `execution-reliability` 的目标/环境证据、`architecture-health` 的边界检查、`tdd-loop` 的行为验证或 Guard 的用户影响门禁；协作者只能补证据，不能替换根因判断。
- 对外返回 `claim_kind`、`recovery_status`、`review_status`、`evidence_refs`、`next_action` 和 `budget`。协作者不可用时使用 `degradation=standalone`，把真正影响判断的缺口写成 `Open`。

