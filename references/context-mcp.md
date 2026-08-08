# Read-Only Context MCP

## Purpose

Expose verified durable-context state to Codex and other MCP-compatible workbenches without creating a second writer or authority. The server starts on demand over stdio and exits with its client.

## Trust Boundary

- Configure one or more exact `--allow-root` values. Parent-directory and arbitrary-path access is rejected.
- Validate the ledger root, task ID, requirements revision/hash, handoff metadata, checkpoint history, and change hash chain on every content query.
- Refuse current-context and search results while the ledger has errors or uncheckpointed warnings.
- Expose no write, remember, checkpoint, switch, sync, or delete tool.
- Keep Obsidian outside the MCP authority path. The server reads only project-local `.agent-context` files and privacy-safe Hook telemetry.

## Automatic Tool Routing

| Need | Tool |
| --- | --- |
| Restore the current objective, acceptance, route, handoff, findings, or decisions | `get_current_context` |
| Find a specific current project fact | `search_context` |
| Diagnose stale context, Hook failures, or compaction verification | `get_context_health` |
| Discover which exact roots this server can read | `list_context_projects` |

Request `include_history=true` only for explicit historical analysis. History returns bounded change/checkpoint summaries rather than full old requirement bodies.

## Stdio Definition

Use `py -3 <skill>/scripts/context_mcp.py --allow-root <exact-project-root>`. Multiple exact roots require repeated `--allow-root` arguments. `DURABLE_CONTEXT_ALLOWED_ROOTS` is an optional path-separator-delimited alternative for hosts that inject environment variables.

The common third-party JSON shape is:

```json
{
  "mcpServers": {
    "durable_context": {
      "command": "py",
      "args": ["-3", "<skill>/scripts/context_mcp.py", "--allow-root", "<exact-project-root>"]
    }
  }
}
```

Keep the exact-root argument aligned with the project currently shared between workbenches. Adding a root expands readable scope and should be an explicit configuration change.
