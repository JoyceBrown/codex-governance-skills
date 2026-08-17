#!/usr/bin/env python3
"""Read-only MCP server for verified durable-context project ledgers."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import context_state


SERVER_NAME = "durable-context-readonly"
SERVER_VERSION = "1.1.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
MIN_BUDGET = 1200
MAX_BUDGET = 16000
DEFAULT_BUDGET = 6000
MAX_QUERY_CHARS = 300
MAX_RESULTS = 20
DEFAULT_HISTORY = 12
MAX_HISTORY = 40


class ContextAccessError(ValueError):
    """A bounded error that is safe to return to an MCP client."""


def canonical_root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def parse_allowed_roots(values: list[str]) -> list[Path]:
    combined = list(values)
    environment = os.environ.get("DURABLE_CONTEXT_ALLOWED_ROOTS", "")
    if environment:
        combined.extend(item for item in environment.split(os.pathsep) if item.strip())
    roots: list[Path] = []
    for value in combined:
        root = canonical_root(value)
        if root not in roots:
            roots.append(root)
    if not roots:
        raise ContextAccessError("at least one --allow-root or DURABLE_CONTEXT_ALLOWED_ROOTS entry is required")
    return roots


def clamp_integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def markdown_section(text: str, title: str) -> str:
    return context_state.requirements_section(text, title).strip()


def current_decisions(text: str) -> str:
    preamble, *chunks = re.split(r"(?m)(?=^###\s+)", text)
    selected: list[str] = []
    for chunk in chunks:
        state = re.search(r"(?mi)^-\s*`state`:\s*([^\r\n]+)$", chunk)
        if state and state.group(1).strip().lower() in {"decided", "active"}:
            selected.append(chunk.strip())
    return "\n\n".join(selected)


def markdown_chunks(source: str, text: str) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    heading = source
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if body and any(item.strip() for item in body):
                chunks.append({"source": source, "heading": heading, "text": "\n".join(body).strip()})
            heading = line.lstrip("#").strip() or source
            body = []
        else:
            body.append(line)
    if body and any(item.strip() for item in body):
        chunks.append({"source": source, "heading": heading, "text": "\n".join(body).strip()})
    return chunks


def budgeted_json(value: dict[str, Any], maximum: int) -> str:
    bounded = json.loads(json.dumps(value, ensure_ascii=False))
    rendered = json.dumps(bounded, ensure_ascii=False, indent=2)
    if len(rendered) <= maximum:
        return rendered
    bounded["truncated"] = True
    bounded["max_chars"] = maximum

    def string_slots(current: Any, path: tuple[Any, ...] = ()) -> list[tuple[int, tuple[Any, ...]]]:
        slots: list[tuple[int, tuple[Any, ...]]] = []
        if isinstance(current, dict):
            for key, item in current.items():
                slots.extend(string_slots(item, path + (key,)))
        elif isinstance(current, list):
            for index, item in enumerate(current):
                slots.extend(string_slots(item, path + (index,)))
        elif isinstance(current, str):
            slots.append((len(current), path))
        return slots

    def replace(path: tuple[Any, ...], content: str) -> None:
        target: Any = bounded
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = content

    for _ in range(200):
        result = json.dumps(bounded, ensure_ascii=False, indent=2)
        if len(result) <= maximum:
            return result
        overflow = len(result) - maximum
        slots = [item for item in string_slots(bounded) if item[0] > 80]
        if not slots:
            fallback = {
                "truncated": True,
                "max_chars": maximum,
                "error": "result metadata exceeded the output budget",
            }
            return json.dumps(fallback, ensure_ascii=False, indent=2)
        length, path = max(slots, key=lambda item: item[0])
        target_length = max(80, length - overflow - 32)
        if target_length >= length:
            target_length = max(80, length // 2)
        target: Any = bounded
        for part in path:
            target = target[part]
        replace(path, context_state.compact_text(str(target), target_length))
    raise ContextAccessError("unable to fit result within max_chars")


def text_result(value: dict[str, Any], maximum: int, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": budgeted_json(value, maximum)}],
        "isError": is_error,
    }


class ContextServer:
    def __init__(self, allowed_roots: list[Path]):
        self.allowed_roots = [canonical_root(root) for root in allowed_roots]

    def resolve_root(self, value: Any = None) -> Path:
        if value is None or not str(value).strip():
            if len(self.allowed_roots) != 1:
                raise ContextAccessError("project_root is required when more than one root is allowed")
            return self.allowed_roots[0]
        requested = canonical_root(str(value))
        if requested not in self.allowed_roots:
            raise ContextAccessError("project_root is outside the configured exact-root allowlist")
        return requested

    def ledger(self, root: Path) -> Path:
        ledger = root / context_state.DEFAULT_DIR
        if not (ledger / "manifest.json").is_file():
            raise ContextAccessError("the allowed project has no durable-context ledger")
        return ledger

    def inspect(self, root: Path, require_clean: bool = True) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        ledger = self.ledger(root)
        errors = context_state.verify(ledger, expected_root=root)
        if errors:
            raise ContextAccessError("ledger verification failed: " + "; ".join(errors))
        consistency = context_state.reconcile(ledger, expected_root=root)
        if consistency.get("errors"):
            raise ContextAccessError("ledger reconciliation failed: " + "; ".join(consistency["errors"]))
        if require_clean and consistency.get("warnings"):
            raise ContextAccessError(
                "ledger has uncheckpointed state and cannot be exported: " + "; ".join(consistency["warnings"])
            )
        manifest = context_state.read_json(ledger / "manifest.json")
        return ledger, manifest, consistency

    @staticmethod
    def metadata(manifest: dict[str, Any], consistency: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": manifest.get("task_id"),
            "objective": manifest.get("task"),
            "status": manifest.get("status"),
            "checkpoint": manifest.get("checkpoint"),
            "requirements_revision": manifest.get("requirements_revision"),
            "requirements_hash": manifest.get("recorded_requirements_hash"),
            "updated_at": manifest.get("updated_at"),
            "consistency": "verified" if consistency.get("valid") else "invalid",
        }

    def history(self, ledger: Path, maximum: int = 20) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in context_state.read_changes(ledger, maximum=100000):
            kind = str(entry.get("kind", ""))
            if kind == "requirement_change":
                events.append(
                    {
                        "kind": kind,
                        "at": entry.get("at"),
                        "revision": entry.get("after_revision"),
                        "category": entry.get("category"),
                        "summary": entry.get("summary"),
                        "requirements_hash": entry.get("requirements_hash"),
                    }
                )
            elif kind == "checkpoint":
                events.append(
                    {
                        "kind": kind,
                        "at": entry.get("at"),
                        "revision": entry.get("revision"),
                        "checkpoint": entry.get("checkpoint"),
                        "status": entry.get("status"),
                        "summary": entry.get("summary"),
                    }
                )
        return events[-maximum:]

    def get_current(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self.resolve_root(arguments.get("project_root"))
        ledger, manifest, consistency = self.inspect(root, require_clean=True)
        requested = arguments.get("sections")
        allowed_sections = {"requirements", "handoff", "findings", "decisions", "execution", "navigation"}
        if requested is None:
            sections = ["requirements", "handoff", "findings", "decisions"]
        elif not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
            raise ContextAccessError("sections must be an array of section names")
        else:
            unknown = sorted(set(requested) - allowed_sections)
            if unknown:
                raise ContextAccessError("unknown sections: " + ", ".join(unknown))
            sections = list(dict.fromkeys(requested))
        maximum = clamp_integer(arguments.get("max_chars"), DEFAULT_BUDGET, MIN_BUDGET, MAX_BUDGET)
        documents: dict[str, Any] = {}
        if "requirements" in sections:
            documents["requirements"] = (ledger / "requirements.md").read_text(encoding="utf-8").strip()
        if "handoff" in sections:
            documents["handoff"] = (ledger / "handoff.md").read_text(encoding="utf-8").strip()
        if "findings" in sections:
            findings = (ledger / "findings.md").read_text(encoding="utf-8")
            documents["verified_findings"] = markdown_section(findings, "Verified")
        if "decisions" in sections:
            decisions = (ledger / "decisions.md").read_text(encoding="utf-8")
            documents["active_decisions"] = current_decisions(decisions)
        if "execution" in sections:
            documents["execution"] = context_state.task_execution_brief(ledger / "task.md", maximum)
        if "navigation" in sections:
            documents["plan_navigation"] = context_state.plan_navigation_view(root)
        result: dict[str, Any] = {
            "authority": "project-local .agent-context ledger",
            "project_root": str(root),
            "metadata": self.metadata(manifest, consistency),
            "sections": documents,
        }
        if bool(arguments.get("include_history")):
            result["history"] = self.history(
                ledger,
                maximum=clamp_integer(arguments.get("max_history"), DEFAULT_HISTORY, 1, MAX_HISTORY),
            )
        result["continuity"] = context_state.continuity_snapshot(root, ledger, manifest)
        return text_result(result, maximum)

    def searchable_documents(
        self,
        root: Path,
        ledger: Path,
        include_history: bool,
        max_history: int = DEFAULT_HISTORY,
    ) -> list[dict[str, str]]:
        requirements = (ledger / "requirements.md").read_text(encoding="utf-8")
        handoff = (ledger / "handoff.md").read_text(encoding="utf-8")
        findings = markdown_section((ledger / "findings.md").read_text(encoding="utf-8"), "Verified")
        decisions = current_decisions((ledger / "decisions.md").read_text(encoding="utf-8"))
        documents: list[dict[str, str]] = []
        for source, text in (
            ("requirements", requirements),
            ("handoff", handoff),
            ("verified_findings", findings),
            ("active_decisions", decisions),
        ):
            documents.extend(markdown_chunks(source, text))
        navigation = context_state.plan_navigation_view(root)
        if navigation.get("configured") and navigation.get("valid"):
            documents.append(
                {
                    "source": "plan_navigation",
                    "heading": "Verified plan navigation",
                    "text": json.dumps(navigation, ensure_ascii=False, indent=2),
                }
            )
        if include_history:
            for item in self.history(ledger, maximum=max_history):
                documents.append(
                    {
                        "source": "history",
                        "heading": f"{item.get('kind')} revision {item.get('revision')}",
                        "text": json.dumps(item, ensure_ascii=False),
                    }
                )
        return documents

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ContextAccessError("query is required")
        if len(query) > MAX_QUERY_CHARS:
            raise ContextAccessError(f"query must not exceed {MAX_QUERY_CHARS} characters")
        root = self.resolve_root(arguments.get("project_root"))
        ledger, manifest, consistency = self.inspect(root, require_clean=True)
        include_history = bool(arguments.get("include_history"))
        limit = clamp_integer(arguments.get("max_results"), 8, 1, MAX_RESULTS)
        maximum = clamp_integer(arguments.get("max_chars"), DEFAULT_BUDGET, MIN_BUDGET, MAX_BUDGET)
        max_history = clamp_integer(arguments.get("max_history"), DEFAULT_HISTORY, 1, MAX_HISTORY)
        lowered = query.casefold()
        terms = [item for item in re.split(r"\s+", lowered) if item]
        matches: list[tuple[int, dict[str, str]]] = []
        documents = self.searchable_documents(root, ledger, include_history, max_history=max_history)
        for document in documents:
            haystack = f"{document['heading']}\n{document['text']}".casefold()
            score = haystack.count(lowered) * 10
            score += sum(haystack.count(term) for term in terms)
            if score:
                matches.append((score, document))
        matches.sort(key=lambda item: (-item[0], item[1]["source"], item[1]["heading"]))
        results = []
        for score, item in matches[:limit]:
            results.append(
                {
                    "source": item["source"],
                    "heading": item["heading"],
                    "score": score,
                    "excerpt": context_state.compact_text(item["text"], 700),
                }
            )
        matched_terms = {term for term in terms if any(term in f"{item['heading']}\n{item['text']}".casefold() for _, item in matches)}
        explicit_conflict = any(
            re.search(r"(?mi)^-\s*status:\s*(?:CONFLICTED|CONFLICT)\s*$", item["text"])
            for _, item in matches[:limit]
        )
        if explicit_conflict:
            recovery_status = "CONFLICTED"
            blocking = True
            next_action = "Stop automatic selection; compare the conflicting sources and record a current decision."
        elif not results:
            recovery_status = "BLOCKED_UNCERTAINTY" if bool(arguments.get("blocking_risk")) else "NOT_FOUND"
            blocking = recovery_status == "BLOCKED_UNCERTAINTY"
            next_action = (
                "Treat the missing context as blocking uncertainty; request an exact source or human decision."
                if blocking
                else "Do not infer historical facts; continue only with an explicit unknown or provide a narrower query."
            )
        elif len(matched_terms) < len(terms):
            recovery_status = "PARTIAL"
            blocking = False
            next_action = "Use only the matched evidence and keep the unresolved portion explicitly unknown."
        else:
            recovery_status = "FOUND"
            blocking = False
            next_action = "Use the verified result excerpts; do not expand to history unless the current evidence is insufficient."
        result = {
            "authority": "project-local .agent-context ledger",
            "project_root": str(root),
            "metadata": self.metadata(manifest, consistency),
            "include_history": include_history,
            "status": recovery_status,
            "searched_scope": ["current-ledger", "verified-project"] + (["explicit-history"] if include_history else []),
            "budget_used": {
                "max_chars": maximum,
                "max_results": limit,
                "max_history": max_history if include_history else 0,
                "documents_scanned": len(documents),
            },
            "blocking": blocking,
            "next_action": next_action,
            "results": results,
        }
        result["continuity"] = context_state.continuity_snapshot(root, ledger, manifest)
        return text_result(result, maximum)

    def health(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self.resolve_root(arguments.get("project_root"))
        ledger = self.ledger(root)
        maximum = clamp_integer(arguments.get("max_chars"), 5000, MIN_BUDGET, MAX_BUDGET)
        errors = context_state.verify(ledger, expected_root=root)
        consistency: dict[str, Any] = {"valid": False, "errors": errors, "warnings": []}
        manifest: dict[str, Any] = {}
        if not errors:
            consistency = context_state.reconcile(ledger, expected_root=root)
            manifest = context_state.read_json(ledger / "manifest.json")
        log_path = ledger / "hook-events.jsonl"
        events: list[dict[str, Any]] = []
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and (
                    not manifest or value.get("task_id") == manifest.get("task_id")
                ):
                    events.append(value)
        durations = [float(item["duration_ms"]) for item in events if isinstance(item.get("duration_ms"), (int, float))]
        counts = Counter(str(item.get("event", "unknown")) for item in events)
        outcomes = Counter(str(item.get("outcome", "unknown")) for item in events)
        reasons = Counter(str(item.get("reason", "unknown")) for item in events)
        p95 = 0.0
        if durations:
            ordered = sorted(durations)
            p95 = ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))]
        recent_compaction = [
            {
                "at": item.get("at"),
                "event": item.get("event"),
                "outcome": item.get("outcome"),
                "reason": item.get("reason"),
                "requirements_revision": item.get("requirements_revision"),
                "requirements_hash": item.get("requirements_hash"),
            }
            for item in events
            if item.get("event") in {"PreCompact", "PostCompact", "SessionStart"}
        ][-12:]
        result = {
            "authority": "project-local .agent-context ledger",
            "project_root": str(root),
            "ledger": {
                "valid": not errors and bool(consistency.get("valid")),
                "errors": consistency.get("errors", errors),
                "warnings": consistency.get("warnings", []),
                "metadata": self.metadata(manifest, consistency) if manifest else {},
            },
            "hooks": {
                "event_count": len(events),
                "events": dict(counts),
                "outcomes": dict(outcomes),
                "top_reasons": dict(reasons.most_common(12)),
                "latency_ms": {
                    "median": round(statistics.median(durations), 3) if durations else 0.0,
                    "p95": round(p95, 3),
                    "maximum": round(max(durations), 3) if durations else 0.0,
                },
                "recent_compaction": recent_compaction,
            },
            "plan_navigation": context_state.plan_navigation_view(root),
            "continuity": context_state.continuity_snapshot(root, ledger, manifest) if manifest and not errors else {},
        }
        return text_result(result, maximum)

    def list_projects(self, arguments: dict[str, Any]) -> dict[str, Any]:
        maximum = clamp_integer(arguments.get("max_chars"), 5000, MIN_BUDGET, MAX_BUDGET)
        projects = []
        for root in self.allowed_roots:
            try:
                ledger = self.ledger(root)
                errors = context_state.verify(ledger, expected_root=root)
                consistency = context_state.reconcile(ledger, expected_root=root) if not errors else {}
                manifest = context_state.read_json(ledger / "manifest.json") if not errors else {}
                project = {
                        "project_root": str(root),
                        "task_id": manifest.get("task_id"),
                        "status": manifest.get("status"),
                        "checkpoint": manifest.get("checkpoint"),
                        "requirements_revision": manifest.get("requirements_revision"),
                        "requirements_hash": manifest.get("recorded_requirements_hash"),
                        "valid": not errors and bool(consistency.get("valid")),
                        "errors": errors or consistency.get("errors", []),
                        "warnings": consistency.get("warnings", []),
                    }
                project["plan_navigation"] = context_state.plan_navigation_view(root)
                project["continuity"] = context_state.continuity_snapshot(root, ledger, manifest) if manifest and not errors else {}
                projects.append(project)
            except (OSError, ValueError) as exc:
                projects.append({"project_root": str(root), "valid": False, "errors": [str(exc)]})
        return text_result({"projects": projects}, maximum)

    @staticmethod
    def tools() -> list[dict[str, Any]]:
        project_root = {
            "type": "string",
            "description": "Exact project root from the server allowlist. Optional when one root is configured.",
        }
        return [
            {
                "name": "get_current_context",
                "description": "Read the current checkpoint-clean durable context. Rejects stale, tampered, or inconsistent ledgers.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_root": project_root,
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["requirements", "handoff", "findings", "decisions", "execution", "navigation"],
                            },
                            "uniqueItems": True,
                        },
                        "include_history": {"type": "boolean", "default": False},
                        "max_history": {"type": "integer", "minimum": 1, "maximum": MAX_HISTORY, "default": DEFAULT_HISTORY},
                        "max_chars": {"type": "integer", "minimum": MIN_BUDGET, "maximum": MAX_BUDGET},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_context",
                "description": "Search current verified project context with bounded FOUND/PARTIAL/NOT_FOUND/CONFLICTED/BLOCKED_UNCERTAINTY status. Historical summaries require include_history=true; an empty result never implies LIKELY_LOST.",
                "inputSchema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
                        "project_root": project_root,
                        "include_history": {"type": "boolean", "default": False},
                        "max_history": {"type": "integer", "minimum": 1, "maximum": MAX_HISTORY, "default": DEFAULT_HISTORY},
                        "blocking_risk": {"type": "boolean", "default": False},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                        "max_chars": {"type": "integer", "minimum": MIN_BUDGET, "maximum": MAX_BUDGET},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_context_health",
                "description": "Read ledger consistency and privacy-safe Hook outcome/latency telemetry, including compaction checks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_root": project_root,
                        "max_chars": {"type": "integer", "minimum": MIN_BUDGET, "maximum": MAX_BUDGET},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "list_context_projects",
                "description": "List only the exact project roots configured for this read-only server and their verification state.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "max_chars": {"type": "integer", "minimum": MIN_BUDGET, "maximum": MAX_BUDGET}
                    },
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        values = arguments if isinstance(arguments, dict) else {}
        try:
            if name == "get_current_context":
                return self.get_current(values)
            if name == "search_context":
                return self.search(values)
            if name == "get_context_health":
                return self.health(values)
            if name == "list_context_projects":
                return self.list_projects(values)
            raise ContextAccessError(f"unknown read-only tool: {name}")
        except (ContextAccessError, OSError, ValueError) as exc:
            maximum = clamp_integer(values.get("max_chars"), 3000, MIN_BUDGET, MAX_BUDGET)
            return text_result({"error": str(exc)}, maximum, is_error=True)

    def resources(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for root in self.allowed_roots:
            try:
                ledger = self.ledger(root)
                manifest = context_state.read_json(ledger / "manifest.json")
                task_id = context_state.validate_task_id(manifest.get("task_id"))
            except (OSError, ValueError):
                continue
            resources.extend(
                [
                    {
                        "uri": f"durable-context://{task_id}/current",
                        "name": f"Current context: {root.name}",
                        "description": "Verified current requirements, handoff, findings, and active decisions.",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": f"durable-context://{task_id}/health",
                        "name": f"Context health: {root.name}",
                        "description": "Ledger consistency and privacy-safe Hook telemetry.",
                        "mimeType": "application/json",
                    },
                ]
            )
        return resources

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "durable-context" or not parsed.netloc:
            raise ContextAccessError("unsupported resource URI")
        task_id = parsed.netloc
        route = parsed.path.strip("/")
        for root in self.allowed_roots:
            try:
                ledger = self.ledger(root)
                manifest = context_state.read_json(ledger / "manifest.json")
            except (OSError, ValueError):
                continue
            if manifest.get("task_id") != task_id:
                continue
            if route == "current":
                result = self.get_current({"project_root": str(root), "max_chars": DEFAULT_BUDGET})
            elif route == "health":
                result = self.health({"project_root": str(root), "max_chars": DEFAULT_BUDGET})
            else:
                raise ContextAccessError("unknown durable-context resource")
            text = str(result.get("content", [{}])[0].get("text", ""))
            if result.get("isError"):
                raise ContextAccessError(text)
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]}
        raise ContextAccessError("resource task_id is not in the configured allowlist")

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = str(message.get("method") or "")
        request_id = message.get("id")
        if request_id is None:
            return None
        try:
            if method == "initialize":
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                requested = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
                result = {
                    "protocolVersion": requested,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": (
                        "Read-only verified project context. Treat the project-local ledger as authority; "
                        "never infer that this server can write or checkpoint state."
                    ),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                result = self.call_tool(str(params.get("name") or ""), params.get("arguments"))
            elif method == "resources/list":
                result = {"resources": self.resources()}
            elif method == "resources/read":
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                result = self.read_resource(str(params.get("uri") or ""))
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ContextAccessError, OSError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(exc)[:1800]},
            }


def serve(server: ContextServer) -> int:
    for raw in sys.stdin.buffer:
        if len(raw) > 1024 * 1024:
            continue
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(message, dict):
            continue
        response = server.handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="durable-context-mcp-") as temporary:
        root = Path(temporary).resolve()
        ledger = root / context_state.DEFAULT_DIR
        context_state.automatic(root, ledger, "start", "MCP regression", "", "", "", "", "active", 3000)
        server = ContextServer([root])
        initialized = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "clientInfo": {"name": "self-test", "version": "1"}},
            }
        )
        if initialized is None or initialized.get("result", {}).get("protocolVersion") != "2025-03-26":
            raise RuntimeError("self-test failed: initialize handshake")
        listed = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [item["name"] for item in listed["result"]["tools"]] if listed else []
        if set(names) != {"get_current_context", "search_context", "get_context_health", "list_context_projects"}:
            raise RuntimeError("self-test failed: unexpected tool surface")
        if any(re.search(r"write|save|update|delete|checkpoint", name, re.IGNORECASE) for name in names):
            raise RuntimeError("self-test failed: mutating MCP tool was exposed")
        current = server.call_tool("get_current_context", {})
        if current.get("isError") or "MCP regression" not in str(current):
            raise RuntimeError("self-test failed: current context query")
        searched = server.call_tool("search_context", {"query": "MCP regression", "include_history": False})
        searched_data = json.loads(searched["content"][0]["text"])
        if searched.get("isError") or searched_data.get("status") != "FOUND" or not searched_data.get("results"):
            raise RuntimeError("self-test failed: current context search")
        missing = server.call_tool("search_context", {"query": "never-present-recovery-marker"})
        missing_data = json.loads(missing["content"][0]["text"])
        if (
            missing.get("isError")
            or missing_data.get("status") != "NOT_FOUND"
            or missing_data.get("blocking")
            or not missing_data.get("searched_scope")
            or not missing_data.get("next_action")
        ):
            raise RuntimeError("self-test failed: bounded NOT_FOUND search contract")
        blocked = server.call_tool(
            "search_context",
            {"query": "never-present-recovery-marker", "blocking_risk": True},
        )
        blocked_data = json.loads(blocked["content"][0]["text"])
        if blocked.get("isError") or blocked_data.get("status") != "BLOCKED_UNCERTAINTY" or not blocked_data.get("blocking"):
            raise RuntimeError("self-test failed: blocking uncertainty search contract")
        health = server.call_tool("get_context_health", {})
        if health.get("isError") or '"valid": true' not in str(health).lower():
            raise RuntimeError("self-test failed: health query")

        valid_plan = """# Active Execution Plan

plan_id: PLAN-01
status: active
authority: exclusive
current_task_id: TASK-01
latest_change_class: task_adjustment
on_complete: wait
route_id: R7
current_route_coordinate: R7:A3/B2
continuity_parent_task_id: none

## Milestones

| Task ID | Status | Route coordinate | Outcome |
| --- | --- | --- | --- |
| TASK-01 | in_progress | R7:A3/B2 | Verify the route. |
"""
        (root / "PLANS.md").write_text(valid_plan, encoding="utf-8")
        current_navigation = server.call_tool("get_current_context", {"sections": ["navigation"]})
        current_navigation_data = json.loads(current_navigation["content"][0]["text"])
        navigation_view = current_navigation_data["sections"]["plan_navigation"]
        if (
            current_navigation.get("isError")
            or navigation_view.get("current_route_coordinate") != "R7:A3/B2"
            or len(str(navigation_view.get("source_hash", ""))) != 64
        ):
            raise RuntimeError("self-test failed: current navigation query")
        navigation_search = server.call_tool("search_context", {"query": "R7:A3/B2"})
        navigation_search_data = json.loads(navigation_search["content"][0]["text"])
        if (
            navigation_search.get("isError")
            or not navigation_search_data.get("results")
            or navigation_search_data["results"][0].get("source") != "plan_navigation"
        ):
            raise RuntimeError("self-test failed: verified navigation search")
        navigation_health = json.loads(server.call_tool("get_context_health", {})["content"][0]["text"])
        if navigation_health["plan_navigation"].get("current_route_coordinate") != "R7:A3/B2":
            raise RuntimeError("self-test failed: navigation health")
        navigation_projects = json.loads(server.call_tool("list_context_projects", {})["content"][0]["text"])
        if navigation_projects["projects"][0]["plan_navigation"].get("current_route_coordinate") != "R7:A3/B2":
            raise RuntimeError("self-test failed: project navigation summary")

        (root / "PLANS.md").write_text(valid_plan.replace("route_id: R7", "route_id: R8"), encoding="utf-8")
        invalid_navigation = server.call_tool("get_current_context", {"sections": ["navigation"]})
        invalid_navigation_data = json.loads(invalid_navigation["content"][0]["text"])
        invalid_view = invalid_navigation_data["sections"]["plan_navigation"]
        if (
            invalid_navigation.get("isError")
            or invalid_view.get("valid")
            or not invalid_view.get("errors")
            or "current_route_coordinate" in invalid_view
        ):
            raise RuntimeError("self-test failed: invalid navigation was exported as trusted")
        invalid_search = json.loads(
            server.call_tool("search_context", {"query": "R7:A3/B2"})["content"][0]["text"]
        )
        if invalid_search.get("results"):
            raise RuntimeError("self-test failed: invalid navigation remained searchable")
        resources = server.resources()
        if len(resources) != 2:
            raise RuntimeError("self-test failed: resources were not exposed")
        if not server.read_resource(resources[0]["uri"]).get("contents"):
            raise RuntimeError("self-test failed: resource read")
        outside = Path(temporary).parent.resolve()
        denied = server.call_tool("get_current_context", {"project_root": str(outside)})
        if not denied.get("isError"):
            raise RuntimeError("self-test failed: root allowlist bypass")
        requirements = ledger / "requirements.md"
        requirements.write_text(requirements.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
        tampered = server.call_tool("get_current_context", {})
        if not tampered.get("isError") or "verification failed" not in str(tampered):
            raise RuntimeError("self-test failed: tampered ledger was exported")
    print("context_mcp self-test passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve verified durable context through read-only MCP stdio.")
    parser.add_argument("--allow-root", action="append", default=[], help="exact project root allowed for read-only access")
    parser.add_argument("--self-test", action="store_true", help="run isolated protocol and boundary regressions")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        roots = parse_allowed_roots(args.allow_root)
    except ContextAccessError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return serve(ContextServer(roots))


if __name__ == "__main__":
    raise SystemExit(main())
