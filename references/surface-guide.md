# Codex project surface guide

Use the smallest surface whose scope matches the information or behavior.

| Surface | Purpose | Typical location | Create when | Do not use for |
| --- | --- | --- | --- | --- |
| Current prompt | One task's goal, context, constraints, and completion condition | Current chat | The requirement is temporary | Durable project facts |
| Global `AGENTS.md` | Personal working preferences across repositories | `~/.codex/AGENTS.md` | The guidance belongs to one developer, not the project | Shared team policy |
| `README.md` | Project overview, setup, and navigation | Repository root | Every user-facing project | Detailed agent policy |
| `docs/` | Product, architecture, data, operations, and decisions | Repository | Detail exceeds the README | Codex runtime settings |
| Root `AGENTS.md` | Durable repository-wide Codex working agreements | Repository root | Commands or constraints should apply broadly | Full project description |
| Nested `AGENTS.md` | Local differences from root guidance | Relevant subtree | The subtree has materially different rules | Repeating root rules |
| `AGENTS.override.md` | Temporary or complete replacement at one instruction level | Beside the `AGENTS.md` it replaces | The ordinary file must be deliberately shadowed | Small additive differences |
| `PLANS.md` | Contract for long, risky, multi-stage implementation plans | Repository root or documented location | Work must survive context changes | Everyday task lists |
| `.codex/config.toml` | Trusted project-specific Codex runtime defaults | `.codex/config.toml` | The repository needs settings different from user defaults | Product facts or secrets |
| Skill | Repeatable task workflow with references or scripts | `.agents/skills/<name>/` | The same non-trivial process recurs | Rules that apply to every task |
| MCP or connector | Live external context or actions | Codex/plugin configuration | Work requires GitHub, Figma, databases, internal services, or other live systems | Static repository documentation |
| Plugin | Installable bundle of skills, tools, MCP, hooks, or assets | Separate plugin package | A capability must be distributed and installed as a unit | A single repository rule |
| Rule | Enforced command decision outside the sandbox | `.codex/rules/*.rules` | A command prefix must be allowed, prompted, or forbidden consistently | Coding style guidance |
| Hook | Deterministic lifecycle action | `.codex/hooks.json` or config | A check must run at a specific agent event | Ordinary tests or CI replacement |
| Custom agent | Narrow delegated role | `.codex/agents/*.toml` | Specialized read-heavy or isolated work recurs | Simple tasks or shared-file editing |
| Scheduled task | Recurring or follow-up execution | Codex Scheduled UI | Work must run later or repeatedly | Durable project documentation |
| Test, linter, CI | Mechanical quality enforcement | Project tooling | A requirement can be checked deterministically | Product intent and tradeoffs |
| Memory | Personal context learned across work | Codex-managed user state | A useful personal fact should carry forward | Authoritative project facts or team rules |
| Managed requirements | Organization-enforced security and feature constraints | Admin-managed `requirements.toml` | An authorized administrator sets policy | Ordinary repository preferences |

## Configuration guardrails

### Project config

Create `.codex/config.toml` only for trusted repository-specific settings. Keep personal model choice, verbosity, and general preferences in user configuration. Never place credentials in repository configuration.

### Instruction overrides

Codex loads at most one instruction file per directory and prefers `AGENTS.override.md` over `AGENTS.md`. Create an override only when replacing that level is intentional; use a nested `AGENTS.md` for additive local guidance.

### Skills

Create a Skill only after identifying a focused repeated workflow, its trigger, its inputs, and its definition of done. Prefer scripts for deterministic repeated mechanics and references for detail loaded on demand.

### MCP

Name the exact external system, required operations, data transmitted, and read/write boundary. Prefer read-only access when sufficient. Do not add a generic MCP placeholder.

### Rules

Use Rules for command execution policy, not prose. Rules are experimental, so keep patterns narrow, include match and non-match examples, and provide safe alternatives for forbidden commands.

### Hooks

Use Hooks when timing is essential, such as scanning before tool use or validating when a turn stops. Explain what runs, what data it sees, failure behavior, and how to disable it.

### Custom agents

Give each agent one narrow role. Prefer read-heavy exploration, review, documentation research, or log analysis. Avoid multiple agents editing the same files.

### Scheduled tasks

Use a standalone task for independent runs and a task in an existing chat when continuity matters. Test the workflow manually first. Use an isolated worktree for unattended code changes when available.

## Outside ordinary project bootstrap

Do not generate personal memories, global guidance, organization-managed requirements, plugin marketplaces, or public plugin packaging from a project brief. Address them only when the user explicitly asks and has the relevant ownership.
