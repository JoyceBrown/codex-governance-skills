# Context Continuity Selection

Use a layered design. No single repository is the default foundation because persistent context has different failure modes: task drift, stale facts, broad codebase discovery, and cross-project recall.

| Layer | Selected contribution | Why | Deliberately excluded |
| --- | --- | --- | --- |
| Task continuity skeleton | Planning with Files | Plain files survive compaction, interruption, and tool changes; no service dependency | Its automatic lifecycle hooks are host-specific and are not assumed here |
| Context discipline | Agent Skills for Context Engineering | Progressive disclosure, compression, retrieval hygiene, and evaluation principles | The skill collection is guidance, not a durable state store |
| Codebase structure | Aider repo-map principles, optional Graphify | Token-budgeted symbols and deterministic AST relationships target code context | A full graph is not created for every task |
| Long-term memory | Claude-Mem observation and retrieval model | Distill events, then retrieve only relevant evidence | Automatic capture, background worker, embeddings, and unreviewed injection |
| Team knowledge base | Optional RAGFlow, Mem0, Cognee, or Letta | Useful when multiple projects, users, or large document collections require governed retrieval | Service startup, embedding cost, privacy risk, and operational complexity in the baseline |

## Repositories Assessed

- Planning with Files: https://github.com/OthmanAdi/planning-with-files
- Claude-Mem: https://github.com/thedotmack/claude-mem
- Claude-Men: https://github.com/JuanLuisLozadaGx/claude-men
- Graphify: https://github.com/Graphify-Labs/graphify
- Understand Anything: https://github.com/Egonex-AI/Understand-Anything
- RAGFlow: https://github.com/infiniflow/ragflow
- DeerFlow: https://github.com/bytedance/deer-flow
- Prime Agent: https://github.com/PrimeIntellect-ai/prime-agent
- Agent Skills for Context Engineering: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
- Aider: https://github.com/Aider-AI/aider
- Mem0: https://github.com/mem0ai/mem0
- Cognee: https://github.com/topoteretes/cognee
- Letta: https://github.com/letta-ai/letta

## Selection Rules

1. Start with the local ledger for task-local continuity.
2. Use a token-budgeted repo map or Graphify only for structural code questions.
3. Add a retrieval service only after the task repeatedly needs cross-session or cross-project recall that the ledger cannot supply.
4. Give every retrieved item a source, timestamp, scope, and verification status before treating it as a decision input.
5. Keep model-generated summaries reversible. The original files, tests, and source documents remain authoritative.

## Rejected As The Default Base

- Prime Agent and DeerFlow are full agent runtimes with daemon, scheduling, tools, and execution ownership. Adopting either as a Codex skill would duplicate or conflict with Codex lifecycle control.
- RAGFlow is an enterprise RAG platform with substantial service and storage requirements. It is justified for document operations, not a single developer's default task memory.
- Understand Anything is valuable for visual onboarding and semantic graph building, but its multi-agent full-repository analysis can consume meaningful tokens. Use it when learning a repository, not before each task.
- Claude-Men follows the same broad worker-memory pattern as Claude-Mem. Prefer evaluating the maintained upstream before relying on a derivative.
