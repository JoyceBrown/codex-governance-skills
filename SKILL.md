---
name: bootstrap-codex-project
description: Turn a software idea or an existing repository into a minimal, accurate, maintainable Codex context system. Use when starting or bootstrapping a project, creating or repairing README.md and AGENTS.md, organizing project documentation, deciding whether nested AGENTS.md files are needed, preparing a long-running project for Codex, or auditing stale and duplicated AI instructions. Generate advanced Codex configuration, skills, rules, hooks, MCP guidance, or custom agents only when project evidence or the user explicitly requires them.
---

# Bootstrap Codex Project

Build the smallest context system that lets a human understand the project and lets Codex work correctly. Ground every artifact in the user's brief or repository facts. Prefer a few accurate files over a complete-looking framework.

## Core model

Keep three semantic layers separate:

1. **Project facts**: `README.md`, `docs/`, code, tests, and decision records explain what the project is and how it works.
2. **Codex guidance**: `AGENTS.md` explains how Codex should work in this repository.
3. **Optional capabilities**: `.codex/`, `.agents/skills/`, MCP, rules, hooks, custom agents, and scheduled tasks exist only for demonstrated needs.

Assign every fact one canonical owner. Link to that owner instead of copying the same explanation into several files.

Use an explicit evidence state whenever a reader could confuse intent with reality:

- **Verified**: observed in repository evidence or a successfully run command.
- **Decided**: supplied by the user or an authoritative project decision.
- **Planned**: accepted direction that is not implemented yet.
- **Assumed**: reversible working assumption that still needs confirmation.
- **Open**: unresolved question or conflicting evidence.

Do not turn filenames, package names, dependencies, or model output into stronger claims than their evidence supports.

## Select the mode

Infer the mode without asking when the situation is clear:

- **Greenfield**: The user provides an idea and the target is empty or not yet created.
- **Existing repository**: Code or project configuration already exists.
- **Audit or refresh**: The user asks to review, simplify, repair, or update existing context files.

For an existing repository, resolve `<skill-dir>` to the directory containing this `SKILL.md`, then run `python "<skill-dir>/scripts/inspect_project.py" <project-root>` before proposing files. Treat its output as evidence, then read only the relevant files it identifies. Do not infer commands, frameworks, paths, or architecture from naming alone.

## Run the workflow

### 1. Establish the project definition

Normalize the available information into:

- purpose and target users
- concrete user outcome
- primary workflow
- scope and explicit non-goals
- technology and deployment facts
- repository map and verified commands
- evidence state for material claims
- quality, safety, and completion requirements
- unresolved decisions

Read `references/interview-and-profiles.md` when important information is missing or when choosing an output profile. Ask no more than three questions at a time, and ask only questions whose answers change the architecture, generated artifacts, or safety posture. When a reversible assumption is sufficient, state it and continue.

### 2. Inspect before writing

For non-empty targets:

1. Read the existing `README.md`, applicable `AGENTS.md`, package manifests, documentation index, test configuration, and CI entry points.
2. Distinguish repository facts from human policy. Derive facts from files; obtain policy from the user or existing authoritative instructions.
3. Preserve accurate human-authored content.
4. Identify contradictions, stale paths, duplicated explanations, and guessed commands.
5. Never overwrite an existing file merely to match a template.

### 3. Choose the smallest output profile

Use one of the profiles defined in `references/interview-and-profiles.md`:

- **Minimal** for small or early projects.
- **Standard** for active multi-module software.
- **Advanced** only for demonstrated tool, safety, automation, or delegation requirements.

Do not equate project size with configuration count. A large project may need only precise documentation and layered `AGENTS.md` files. A small high-risk project may need rules or hooks.

### 4. Present the artifact plan

Before broad edits, show a compact plan with four groups:

- create
- update
- keep unchanged
- intentionally skip

Give one reason for each non-obvious file. If the user explicitly requested generation, proceed after the plan unless an existing file would be replaced, a security-sensitive setting would change, or a consequential command would run. Confirm those cases before acting.

### 5. Generate semantic artifacts

Use the matching files under `assets/templates/` as structural starting points. Adapt them to the project; do not leave unused sections or template placeholders.

Apply these ownership rules:

- Put the short project introduction, setup, and navigation in `README.md`.
- Put product behavior and boundaries in `docs/product.md`.
- Put module boundaries and data flow in `docs/architecture.md`.
- Put entity meaning and invariants in `docs/data-model.md` when the domain is non-trivial.
- Put ambiguous domain terms in `docs/glossary.md`.
- Put durable decisions and tradeoffs in `docs/decisions/`.
- Put current temporary progress in `docs/work/current.md`, not in permanent guidance.
- Put repository-wide working rules, verified commands, constraints, and completion checks in root `AGENTS.md`.
- Add a nested `AGENTS.md` only when that subtree has materially different commands, constraints, ownership, or risk.
- Use `PLANS.md` only when long or risky work benefits from a durable execution-plan contract.

Read `references/surface-guide.md` before adding any optional Codex surface. Never generate project-local model preferences, broad permissions, external integrations, hooks, command rules, or custom agents from a vague project description.

### 6. Keep instructions operational

Write `AGENTS.md` as an operational index, not a project encyclopedia:

- Reference authoritative docs instead of repeating them.
- Include commands only after verifying them.
- Express constraints as observable behavior.
- Put formatting and mechanical checks in tooling or CI when possible.
- Keep global rules at the root and local differences near their scope.
- Remove vague rules such as "write good code" or "follow best practices".

Match the language of generated human-facing documents to the user's language unless the repository already has a clear documentation language policy.

### 7. Validate

Run:

```text
python "<skill-dir>/scripts/validate_project_context.py" <project-root> --profile <minimal|standard|advanced>
```

Then verify:

- every referenced path exists or is explicitly marked as planned
- every command is present in project configuration or has been successfully run
- no `{{PLACEHOLDER}}` remains
- no concept has conflicting definitions across files
- nested `AGENTS.md` files add local information instead of duplicating the root
- no secrets, personal absolute paths, or unsafe permission defaults were introduced
- relevant project tests or checks pass when implementation files changed

Treat validator warnings as review prompts, not automatic failures. Fix errors and explain any intentionally retained warning.

### 8. Report the result

Summarize:

- files created or updated
- assumptions made
- advanced surfaces deliberately omitted
- validation performed
- decisions still requiring the user

Do not claim the project is fully configured when commands, deployment, security, or external integrations remain unverified.

## Guardrails

- Do not generate every possible file.
- Do not create one `AGENTS.md` per folder.
- Do not copy product descriptions into `AGENTS.md`.
- Do not invent scripts, package commands, directory names, or technology choices.
- Do not add dependencies solely to support this context system.
- Do not store credentials or tokens in generated files.
- Do not enable full-access sandboxing or approval bypasses.
- Do not add MCP servers, hooks, rules, plugins, agents, or automations without a concrete use case and an explained trust boundary.
- Do not overwrite human-authored files without preserving their intent and showing the change.
- Do not initialize Git, commit, push, deploy, or install packages unless the user requested that broader action.

## Reference routing

- Read `references/interview-and-profiles.md` for discovery questions, profile selection, and artifact criteria.
- Read `references/surface-guide.md` only when deciding where information belongs or whether advanced Codex surfaces are justified.
- Read `references/design-sources.md` only when maintaining this skill or explaining how its design relates to existing open-source approaches.
