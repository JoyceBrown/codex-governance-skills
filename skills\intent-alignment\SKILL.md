---
name: intent-alignment
description: 在需求含糊、目标变化、跨会话恢复或验收标准不清时，把用户意图压缩为目标、可见成功状态、范围、非目标、约束和未知；不替用户做未授权决定。
---

# Intent Alignment

把“我要它工作”变成可验证的下一步，但不要把澄清过程扩写成第二套计划或记忆系统。

## 什么时候使用

- 用户的目标、优先级、范围或完成标准互相冲突。
- 继续旧项目时需要区分当前要求、旧决定、路线图和未知。
- 任务跨多个 Skill、提供者、仓库或用户路径，需要统一成功定义。

简单问题和目标已经明确的局部编辑不要启动本 Skill。

## 输出

输出一个短的对齐卡：

```text
goal: 用户真正要完成的事情
visible_success: 用户最后能看到或做到什么
scope / non_goals: 本轮包含和排除
constraints: 已确认的权限、兼容、成本和时间边界
intent_status: DECIDED | ASSUMED | OPEN | CONFLICTED
unknowns: 仍需验证的事实
next_action: 一个最小可执行动作
```

用户明确说出的目标可以是 `DECIDED`；模型推断只能是 `ASSUMED`。冲突不靠投票解决，标为 `CONFLICTED` 并指出需要谁决定。

## 边界

只读分析，不修改代码、计划、账本、配置或外部系统。将结果交给 Bootstrap、Durable 或 Guard 时只传字段和证据引用，不传原始聊天。没有足够信息时提出最多三个真正会改变结果的问题，否则采用可逆假设并标明。

