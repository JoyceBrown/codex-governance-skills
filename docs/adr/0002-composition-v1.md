# ADR 0002: 有界组合协议

组合只交换结构化信封、证据引用和一个最小下一动作。路由选一个主技能，调用深度最多 2，兄弟调用共享父预算。`execution_status=COMPLETED` 只表示当前动作执行结束；用户目标是否被接受必须由 `outcome_status` 或本地完成收据另行证明。

语义验证以 `scripts/validate-composition.py` 为准，结构可被 `docs/composition.schema.json` 预检。组合失败回退到主技能的 standalone 流程或明确标记阻塞。
