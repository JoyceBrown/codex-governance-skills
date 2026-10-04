# TDD 案例

## 测试通过不等于用户完成

单元测试和集成测试都通过，但安装后的真实用户路径没有执行时，动作可以是 `COMPLETED`，用户路径仍是 `UNKNOWN`，整体只能报告 `PARTIAL`。

## 最小切片

先保留可复现的失败检查，再做最小实现和受影响回归。测试只覆盖用户授权范围，不自动安装陌生依赖、发布或提交。

## 独立回退

没有 Diagnose、Execution Reliability 或 Guard 时，TDD 仍可以完成本地红-绿-回归；外部结果和授权缺口必须保持 `UNKNOWN` 或 `PARTIAL`。
