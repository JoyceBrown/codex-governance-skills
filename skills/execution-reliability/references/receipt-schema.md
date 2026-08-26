# 执行收据

收据是当前任务的短证据索引，不是记忆库、任务数据库或完整日志。建议结构：

```json
{
  "schema": "execution-reliability-receipt-v1",
  "request_id": "turn-or-task-id",
  "status": "READY | WARN | BLOCKED | PARTIAL",
  "risk": "low | medium | high | critical",
  "scope": "current action scope",
  "target": "redacted label",
  "checks": [{"id": "path.exists", "status": "PASS", "evidence": "digest-or-safe-summary"}],
  "attempt": 1,
  "retry": "not-needed | allowed-once | stopped | ask",
  "review_candidate": "NONE | POSSIBLE | REQUIRED",
  "next_action": "one smallest safe action",
  "generated_at": "ISO-8601"
}
```

不要写原始提示、完整命令行、环境变量值、访问令牌、完整日志、聊天记录或私有源码。若收据需要持久化，调用方必须明确给出项目外或项目已授权的目标，并把它作为证据引用交给 `durable-context`，不能绕过其生命周期写入 `.agent-context`。
