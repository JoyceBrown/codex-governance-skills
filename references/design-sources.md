# Design sources and synthesis

This skill adopts concepts from public open-source projects without copying their implementation or templates.

## Official Codex foundation

The surface names and discovery behavior follow the current official documentation for [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Skills](https://learn.chatgpt.com/docs/build-skills), [project configuration and hooks](https://learn.chatgpt.com/docs/config-file/config-advanced), [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules), and [custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Open-source synthesis

| Source | Retained idea | Deliberately simplified or rejected |
| --- | --- | --- |
| [GitHub Spec Kit](https://github.com/github/spec-kit) | Separate principles, specification, plan, tasks, and implementation; clarify before committing to architecture | Do not require a full spec-driven ceremony for every project |
| [Caliber](https://github.com/caliber-ai-org/ai-setup) | Audit before writing, ground paths and commands in the repository, preview changes, preserve recoverability | Do not generate parallel configuration for every agent platform |
| [AgentRules Architect](https://github.com/trevor-nichols/agentrules-architect) | Analyze repository facts deeply; use durable plans for long work | Do not run a model-heavy multi-agent pipeline by default |
| [AGENTS.md Generator](https://github.com/Eriemon/agents-md-generator) | Keep root guidance concise, create scoped guidance only when needed, separate human policy from repository facts | Do not add registries, databases, remote governance, or strong-control machinery to ordinary projects |
| [Project Bootstrapper](https://github.com/mhattingpete/claude-skills-marketplace) | Cover project structure, documentation, tests, quality tooling, and CI as a coherent setup | Do not install every best-practice tool or generate unused documents |
| [TechWolf AI-First Toolkit](https://github.com/techwolf-ai/ai-first-toolkit) | Ask decision-impact questions and choose the smallest useful architecture | Replace Claude-specific paths and assumptions with Codex-native surfaces |

## Unified definition

The result is not an "AI configuration bundle." It is a semantic project context system:

1. Project facts have one authoritative home.
2. Codex guidance is short, scoped, and operational.
3. Optional capabilities appear only after a concrete need exists.
4. Repository evidence overrides guessed templates.
5. Humans can understand and maintain every generated artifact.

## Internal design standard

`skill-design-principles.md` is the maintenance standard distilled from the user discussion that produced this Skill. Its central rule is that the Skill's diagnostic ability should be comprehensive while its generated structure remains minimal and evidence-based. It also defines natural-language entry, progressive disclosure, evidence states, planning authority, validation-based completion, and safe degradation for cases the workflow cannot classify confidently.
