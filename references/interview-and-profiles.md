# Discovery and output profiles

## Discovery rule

Ask only for missing information that changes the result. Prefer repository evidence for technical facts and user answers for product intent or policy.

## Decision-impact questions

| Missing area | Ask when | Example question |
| --- | --- | --- |
| User and problem | The project purpose is ambiguous | Who will use this, and what concrete problem should it solve first? |
| Primary workflow | Several products could fit the description | What is the one end-to-end action the first release must complete? |
| Scope | The brief lists many features | Which capabilities belong in the first usable release, and which are explicitly out? |
| Runtime shape | It changes the architecture | Is this local-only, a hosted service, a desktop app, or a library? |
| Data sensitivity | Personal, financial, medical, or production data may be involved | What sensitive data exists, and where may it be stored or transmitted? |
| Collaboration | Auth, roles, or workflow may change | Is this for one person or multiple users with different permissions? |
| Commands | The repository does not establish them | What are the authoritative install, start, test, and build commands? |
| Deployment | Operations documentation may be needed | Where will the project run, and who operates it? |
| Current focus | Several plans or todo lists could appear active | What do you want Codex to finish first right now? |
| Completion routing | Work should continue across plans or sessions | When that work is done, should Codex stop for review, return to a named task, or start another named task? |
| Temporary exclusions | The user is reprioritizing work | Which areas should Codex leave alone for now? |

Do not ask about choices that can be deferred safely. Mark unresolved decisions in the relevant document instead.

## Minimal profile

Use for a small, early, or single-module project.

Create or repair:

- `README.md`
- root `AGENTS.md`

Add `docs/INDEX.md`, `docs/product.md`, or `docs/architecture.md` only when the corresponding detail no longer fits clearly in `README.md`. Skip empty documents.

## Standard profile

Use when the project has multiple modules, meaningful domain terminology, persistent data, deployment concerns, or a team workflow.

Create or repair the minimal files plus:

- `docs/INDEX.md`
- `docs/product.md`
- `docs/architecture.md`

Then add only relevant items:

- `docs/data-model.md` for non-trivial entities and invariants
- `docs/glossary.md` for ambiguous domain language
- `docs/testing.md` for multiple test layers or special test environments
- `docs/operations.md` for deployment, backup, observability, or recovery
- `docs/decisions/` for durable architectural choices
- `PLANS.md` for long-running execution plans
- `docs/roadmap.md` only when long-term outcomes need a separate non-executable owner
- `docs/work/current.md` for cross-session checkpoint state, never as a second task source
- nested `AGENTS.md` files for materially different subtrees

When planning artifacts are needed, read `planning-authority.md`. Do not enable that module merely because the project is Standard.

## Advanced profile

Use only when the project has a concrete need that ordinary documentation, tests, and CI cannot satisfy.

Start with the standard profile. Select each advanced surface independently; the profile name never requires generating every surface.

Possible additions:

- `.codex/config.toml` for trusted repository-specific Codex settings
- `.agents/skills/` for repeated project workflows
- `.codex/rules/` for command-level allow, prompt, or forbid decisions
- `.codex/hooks.json` for lifecycle-triggered deterministic checks
- `.codex/agents/` for narrow delegated roles
- MCP configuration for live external tools or data
- scheduled tasks for recurring or monitoring work

Advanced does not mean generate all of these. Select each one independently using `surface-guide.md`.

Planning authority is not inherently Advanced. It is an independent module selected from demonstrated planning complexity or repeated plan confusion, not from project prestige or team size.

## Nested AGENTS.md test

Create a nested file only when at least one answer is yes:

1. Does the subtree use different authoritative commands?
2. Does it have different architecture or dependency boundaries?
3. Does it have special safety, compliance, or data-handling rules?
4. Does a different team own it with durable conventions?
5. Would the root rule become confusing if expressed globally?

If none apply, keep one root file.

## Artifact plan format

Use this compact structure:

```text
Create
- docs/product.md: product behavior is not documented.

Update
- README.md: startup command is stale.

Keep
- docs/architecture.md: current and consistent with the code.

Skip
- .codex/hooks.json: no lifecycle automation requirement.
```
