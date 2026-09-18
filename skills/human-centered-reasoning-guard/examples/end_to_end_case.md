# End-to-End Case: Session Continuity Failure

本案例专门演示两个最容易被写成“伪结构差异”的模型如何被真正区分，并演示第一轮实验失败后的第二轮 Reasoning。

## 1. 触发

当前表现：新一轮 Session 看起来仍有旧会话身份，但实际工作区/Runtime 执行状态不一致。

宿主廉价信号：

```text
same_region_modifications = 4
acceptance_unchanged_iterations = 2
user_outcome_complete = false
```

因此满足两个以上廉价风险信号，进入 HCR。

## 2. WHY / WHAT

```text
WHY：保证跨 Session 工作连续性。

WHAT：重新打开后：
1. 定位正确项目；
2. 定位正确会话；
3. 恢复正确 Runtime 状态；
4. 能继续工作。
```

## 3. Epistemic State

```text
OBSERVATION：
新 Session 显示旧会话身份，但执行环境表现异常。

FACT：
旧 Session 标识存在；部分文件可见。

UNKNOWN：
究竟是 Session Identity、Workspace Binding、Runtime Binding
还是它们之间的恢复顺序导致异常。

CURRENT MODEL：
“保存的 session 信息不完整。”
```

注意：最后一句只是当前模型，不是事实。

## 4. Zero-Token Replay

Replay 查到三条历史 HOW：

```text
E1：只保存 session_id → partial
E2：session + workspace + runtime binding → success
E3：只依赖 context.md → failure
```

Replay 发现 E2 在同一环境 scope 下曾取得最高 goal_progress，因此优先级最高。

但是当前运行仍有一个异常：E2 曾成功，并不证明当前故障一定由“字段不完整”造成。

## 5. 第一轮 Structural Reasoning

当前模型需要两个真正不同维度的候选。

### M1：状态权威模型

核心假设：

> Runtime Binding 才是恢复执行环境的权威状态；Session / Workspace 只是定位信息。

改变维度：

```text
authoritative_state
```

预测：

> 即使 session_id 和 workspace_id 正确，只要 Runtime Binding 错误，仍然会复现“身份正常、执行环境错误”。

### M2：生命周期/因果时序模型

核心假设：

> 恢复顺序错误：系统先重建 Session，再派生 Workspace/Runtime 状态，导致后续派生状态基于过期上下文。

改变维度：

```text
temporal_order
causal_mechanism
```

预测：

> 保持相同最终数据，但交换“恢复 Runtime Binding”和“重建 Session”的顺序，会改变结果。

这两个模型不再只是“Binding 从哪里来”的变体：

```text
M1 = 谁拥有权威状态？
M2 = 恢复过程的因果顺序是什么？
```

## 6. 第一轮最小判别实验

实验：

```text
保持 session_id / workspace_id 不变
仅替换/重建 runtime_binding
```

这是一个候选的低风险、可逆、范围明确的判别实验。只有在当前
Guard 事实门已经确认目标身份、回滚点和同范围授权后，才可按既有授权执行；
本案例本身不会授予替换或重建 Runtime Binding 的权限。否则只返回验证请求。

### 结果

实验失败：Runtime Binding 修正后异常仍然存在。

因此：

```text
M1 被明显削弱/部分证伪。
M2 暂存。
```

实验本身是新的 OBSERVATION，不是“任务失败”。

## 7. 第二轮 Reasoning

不能简单再次说“可能还有 Binding 问题”。必须利用新证据改变推理维度。

保留：

```text
session_id 正确
workspace_id 正确
runtime_binding 修正仍失败
```

淘汰：

```text
“Runtime Binding 单独就是决定性根因”
```

重新建立两个模型：

### M3：派生快照模型

> Session 恢复时读取了一个旧的状态快照；即使 Runtime Binding 后续修正，已经派生出的 Context/Tool Registry 没有重新生成。

改变维度：

```text
information_flow
state_derivation
```

预测：

> 清除派生快照但不改变身份信息后，重新初始化 Runtime，异常消失。

### M4：Authority Split 模型

> 系统存在两个同时生效的状态权威：一份由 Session 持有，另一份由 Runtime/Workspace 持有；两者值都“看起来正确”，但执行时读取了不同权威。

改变维度：

```text
authoritative_state
system_boundary
ownership
```

预测：

> 追踪执行请求最终读取的唯一状态源后，会发现它与 UI/Session 显示的状态源不同。

## 8. 第二轮判别实验

优先选择最小实验：

```text
不改用户数据；
不改权限；
只打印/读取“执行请求最终使用的权威状态源”；
比较 UI 展示状态 vs Runtime 实际读取状态。
```

仍属于低风险、可逆诊断；在同范围授权存在时可执行，否则只提交给现有
Guard/项目所有者审议。读取状态源本身不改变项目事实，也不能绕过身份门禁。

## 9. Verification

最终无论哪一个模型成立，都必须同时验证：

```text
Implementation Verification：实现修改/诊断是否正确。
Requirement Verification：用户要求的连续性条件是否满足。
User Outcome Verification：用户是否真的可以继续工作。
```

## 10. Writeback

将以下作为一条经过脱敏的候选观察返回给现有 Experience/Review owner；
只有该 owner 的既有追加、审查和晋升流程可以决定是否持久化：

```text
观察：在当前隔离实验范围内，Runtime Binding 单独不足以解释故障。

被削弱模型：M1。

保留候选：M2 / M3 / M4。

环境：desktop-codex（仅作为当前 scope 标签，不代表全局适用）。

边界：仅适用于当前项目与当时 Runtime 状态。
```

不要写成：

```text
“根因就是 M4。”
```

除非现实实验真的支持它。
