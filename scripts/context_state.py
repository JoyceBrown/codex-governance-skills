#!/usr/bin/env python3
"""Create and validate a small, project-scoped durable context ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DIR = ".agent-context"
REQUIRED_FILES = (
    "task.md",
    "requirements.md",
    "findings.md",
    "decisions.md",
    "handoff.md",
    "history.jsonl",
    "changes.jsonl",
    "manifest.json",
)
TRACKED_FILES = ("task.md", "requirements.md", "findings.md", "decisions.md", "handoff.md")
MAX_FIELD_LENGTH = 4000
MAX_REQUIREMENTS_LENGTH = 12000
LEDGER_VERSION = 6
RECOVERY_STATUSES = (
    "FOUND",
    "PARTIAL",
    "NOT_FOUND",
    "CONFLICTED",
    "LIKELY_LOST",
    "BLOCKED_UNCERTAINTY",
)
RECOVERY_TIERS = (
    {"tier": 0, "name": "current-ledger", "scope": ("requirements", "handoff", "task")},
    {"tier": 1, "name": "verified-project", "scope": ("findings", "decisions", "plan")},
    {"tier": 2, "name": "explicit-history", "scope": ("changes", "history")},
)
MAX_REFERENCE_ITEMS = 12
RESEARCH_RECEIPT_STATUSES = {"VALID", "EXPIRED", "CONFLICTED", "SUPERSEDED"}
TASK_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
PLAN_FIELD_RE = re.compile(
    r"^\s*(plan_id|status|authority|current_task_id|latest_change_class|on_complete|route_id|current_route_coordinate|continuity_parent_task_id)\s*:\s*(.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PLAN_ROUTE_ID_RE = re.compile(r"^R[1-9][0-9]*$")
PLAN_ROUTE_COORDINATE_RE = re.compile(
    r"^(?P<route>R[1-9][0-9]*):A(?P<a>[1-9][0-9]*)"
    r"(?:/B(?P<b>[1-9][0-9]*))?(?:/C(?P<c>[1-9][0-9]*))?$"
)
PLAN_MAX_BYTES = 1024 * 1024

# The project fingerprint is deliberately bounded.  It detects ordinary source and
# configuration drift without turning every Hook invocation into a full repository
# index or storing file contents in the ledger.
PROJECT_SCAN_EXCLUDED_DIRS = {
    ".agent-context",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
PROJECT_SCAN_SUFFIXES = {
    ".bat", ".c", ".cc", ".cfg", ".cmd", ".conf", ".cpp", ".cs", ".css",
    ".gradle", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json",
    ".jsx", ".kt", ".md", ".mjs", ".ps1", ".py", ".pyi", ".rs", ".scss",
    ".sh", ".sql", ".svelte", ".swift", ".toml", ".ts", ".tsx", ".txt",
    ".vue", ".xml", ".yaml", ".yml",
}
PROJECT_SCAN_NAMES = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Procfile", "requirements.txt",
}
PROJECT_SCAN_MAX_FILES = 512
PROJECT_SCAN_MAX_BYTES = 4 * 1024 * 1024
PROJECT_SCAN_MAX_FILE_BYTES = 512 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_text(value: str, field: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    if len(text) > MAX_FIELD_LENGTH:
        raise ValueError(f"{field} must be at most {MAX_FIELD_LENGTH} characters")
    return text


def require_task(value: str) -> str:
    text = require_text(value, "task")
    if "\n" in text or "\r" in text or re.search(r"(?m)^\s*##\s+", text):
        raise ValueError("task objective must be a single line without Markdown headings")
    return text


def require_requirements(value: str, field: str = "requirements") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    if len(text) > MAX_REQUIREMENTS_LENGTH:
        raise ValueError(f"{field} must be at most {MAX_REQUIREMENTS_LENGTH} characters")
    return text


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_path(value: Any, field: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return Path(text).expanduser().resolve()


def validate_task_id(value: Any) -> str:
    task_id = str(value or "").strip()
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("task_id must be a 32-character lowercase hexadecimal id")
    return task_id


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hashes(context_dir: Path) -> dict[str, str]:
    return {
        name: file_hash(context_dir / name)
        for name in TRACKED_FILES
        if (context_dir / name).is_file()
    }


def append_change(context_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = context_dir / "changes.jsonl"
    previous_hash = ""
    if path.is_file():
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                previous = json.loads(line)
            except json.JSONDecodeError:
                break
            if isinstance(previous, dict):
                previous_hash = str(previous.get("event_hash", ""))
            break
    enriched = dict(payload)
    enriched["previous_event_hash"] = previous_hash
    enriched["event_hash"] = change_event_hash(enriched)
    append_jsonl(path, enriched)
    return enriched


def initial_requirements(task: str) -> str:
    return "\n".join(
        (
            "# Current Requirements",
            "",
            "## Objective",
            task,
            "",
            "## Acceptance Standard",
            "- [ ] Define the completion evidence.",
            "",
            "## Current Route",
            "- [ ] Inspect current state and identify the first concrete phase.",
            "",
            "## Current Revision",
            "0",
            "",
        )
    )


def requirements_revision(manifest: dict[str, Any]) -> int:
    value = manifest.get("requirements_revision", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def markdown_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    preamble: list[str] = []
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading:
                sections.append((heading, "\n".join(body).strip()))
            elif body:
                preamble.extend(body)
            heading = line[3:].strip()
            body = []
        else:
            body.append(line)
    if heading:
        sections.append((heading, "\n".join(body).strip()))
    elif body:
        preamble.extend(body)
    return "\n".join(preamble).strip(), sections


def plan_fields(text: str) -> dict[str, str]:
    return {
        key.lower(): value.strip()
        for key, value in PLAN_FIELD_RE.findall(text)
    }


def plan_field_duplicates(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in PLAN_FIELD_RE.findall(text):
        values.setdefault(key.lower(), []).append(value.strip())
    return {key: entries for key, entries in values.items() if len(entries) > 1}


def split_plan_table_row(line: str) -> list[str]:
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return []
    return [cell.strip() for cell in value[1:-1].split("|")]


def plan_milestones(text: str) -> tuple[list[dict[str, str]], bool]:
    _, sections = markdown_sections(text)
    body = next((value for name, value in sections if name.casefold() == "milestones"), "")
    lines = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], False
    headers = [re.sub(r"\s+", " ", item.strip().lower()) for item in split_plan_table_row(lines[0])]
    if "task id" not in headers or "status" not in headers:
        return [], False
    coordinate_header = next(
        (name for name in ("route coordinate", "coordinate") if name in headers),
        None,
    )
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = split_plan_table_row(line)
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        task_id = row.get("task id", "").strip()
        status = row.get("status", "").strip().lower()
        if not task_id or status not in {"pending", "in_progress", "completed", "blocked", "deferred"}:
            continue
        rows.append(
            {
                "task_id": task_id,
                "status": status,
                "coordinate": row.get(coordinate_header, "").strip() if coordinate_header else "",
            }
        )
    return rows, coordinate_header is not None


def inspect_plan_navigation(root: Path) -> dict[str, Any]:
    plan_path = root.resolve() / "PLANS.md"
    result: dict[str, Any] = {
        "configured": False,
        "valid": True,
        "source": "PLANS.md",
        "authority": "active exclusive root PLANS.md (read-only navigation)",
        "errors": [],
    }
    if not plan_path.is_file():
        result["reason"] = "PLANS.md not found"
        return result
    try:
        if plan_path.stat().st_size > PLAN_MAX_BYTES:
            raise ValueError(f"PLANS.md exceeds {PLAN_MAX_BYTES} bytes")
        raw = plan_path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        result.update({"configured": True, "valid": False, "errors": [str(exc)]})
        return result

    result["source_hash"] = hashlib.sha256(raw).hexdigest()
    fields = plan_fields(text)
    navigation_keys = (
        "route_id",
        "current_route_coordinate",
        "continuity_parent_task_id",
    )
    rows, has_coordinate_column = plan_milestones(text)
    configured = any(fields.get(key, "").strip() for key in navigation_keys)
    if has_coordinate_column and any(
        row["coordinate"].strip().lower() not in {"", "none", "-"}
        for row in rows
    ):
        configured = True
    result["configured"] = configured
    if not configured:
        result["reason"] = "plan navigation is not configured"
        return result

    errors: list[str] = []
    duplicates = plan_field_duplicates(text)
    if duplicates:
        errors.extend(f"duplicate plan field: {name}" for name in sorted(duplicates))

    for name in ("plan_id", "current_task_id", "route_id", "current_route_coordinate", "on_complete"):
        if not fields.get(name, "").strip():
            errors.append(f"missing plan navigation field: {name}")
    if fields.get("status", "").strip().lower() != "active":
        errors.append("PLANS.md is not active")
    if fields.get("authority", "").strip().lower() != "exclusive":
        errors.append("PLANS.md does not have exclusive authority")

    route_id = fields.get("route_id", "").strip()
    coordinate = fields.get("current_route_coordinate", "").strip()
    coordinate_match = PLAN_ROUTE_COORDINATE_RE.fullmatch(coordinate)
    if route_id and not PLAN_ROUTE_ID_RE.fullmatch(route_id):
        errors.append("invalid route_id")
    if coordinate and coordinate_match is None:
        errors.append("invalid current_route_coordinate")
    elif coordinate_match and route_id and coordinate_match.group("route") != route_id:
        errors.append("current_route_coordinate does not match route_id")

    current_task = fields.get("current_task_id", "").strip()
    in_progress = [row for row in rows if row["status"] == "in_progress"]
    if len(in_progress) != 1:
        errors.append(f"expected one in_progress milestone, found {len(in_progress)}")
    elif in_progress[0]["task_id"] != current_task:
        errors.append("in_progress milestone does not match current_task_id")

    row_by_task = {row["task_id"]: row for row in rows}
    coordinate_by_task: dict[str, str] = {}
    seen_coordinates: set[str] = set()
    if has_coordinate_column:
        for row in rows:
            value = row["coordinate"].strip()
            if value.lower() in {"", "none", "-"}:
                continue
            match = PLAN_ROUTE_COORDINATE_RE.fullmatch(value)
            if match is None:
                errors.append(f"invalid milestone route coordinate for {row['task_id']}")
                continue
            if route_id and match.group("route") != route_id:
                errors.append(f"milestone route coordinate does not match route_id for {row['task_id']}")
            if value in seen_coordinates:
                errors.append("duplicate milestone route coordinate")
            seen_coordinates.add(value)
            coordinate_by_task[row["task_id"]] = value
        if current_task and current_task not in coordinate_by_task:
            errors.append("current task is missing a milestone route coordinate")
        elif current_task and coordinate and coordinate_by_task.get(current_task) != coordinate:
            errors.append("current task milestone coordinate does not match current_route_coordinate")

    continuity_parent = fields.get("continuity_parent_task_id", "").strip()
    is_continuity = bool(coordinate_match and coordinate_match.group("c"))
    if is_continuity:
        if not continuity_parent or continuity_parent.lower() in {"none", "-"}:
            errors.append("continuity work requires continuity_parent_task_id")
        else:
            parent = row_by_task.get(continuity_parent)
            if parent is None:
                errors.append("continuity parent is not in Milestones")
            elif parent["status"] not in {"deferred", "blocked"}:
                errors.append("continuity parent is not deferred or blocked")
            if fields.get("on_complete", "").strip() != f"resume:{continuity_parent}":
                errors.append("continuity on_complete does not resume its parent task")
        if fields.get("latest_change_class", "").strip().lower() != "priority_branch":
            errors.append("continuity work is not classified as priority_branch")
    elif continuity_parent and continuity_parent.lower() not in {"none", "-"}:
        errors.append("continuity_parent_task_id is set outside a C coordinate")

    if errors:
        result.update({"valid": False, "errors": sorted(set(errors))})
        return result
    result.update(
        {
            "plan_id": fields["plan_id"],
            "route_id": route_id,
            "current_task_id": current_task,
            "current_route_coordinate": coordinate,
            "continuity_parent_task_id": (
                continuity_parent
                if continuity_parent and continuity_parent.lower() not in {"none", "-"}
                else None
            ),
            "on_complete": fields["on_complete"],
        }
    )
    return result


def plan_navigation_view(root: Path) -> dict[str, Any]:
    navigation = inspect_plan_navigation(root)
    result: dict[str, Any] = {
        "configured": bool(navigation.get("configured")),
        "valid": bool(navigation.get("valid")),
        "source": navigation.get("source"),
        "authority": navigation.get("authority"),
    }
    if not navigation.get("configured"):
        result["reason"] = navigation.get("reason", "plan navigation is not configured")
        return result
    if not navigation.get("valid"):
        result["errors"] = list(navigation.get("errors", []))
        return result
    for key in (
        "source_hash",
        "plan_id",
        "route_id",
        "current_task_id",
        "current_route_coordinate",
        "continuity_parent_task_id",
        "on_complete",
    ):
        if navigation.get(key) is not None:
            result[key] = navigation[key]
    return result


def git_revision(root: Path) -> str | None:
    """Read the current Git revision without invoking a process or changing state."""
    git_path = root / ".git"
    try:
        if git_path.is_file():
            pointer = git_path.read_text(encoding="utf-8").strip()
            if pointer.startswith("gitdir:"):
                git_path = (root / pointer.split(":", 1)[1].strip()).resolve()
        head = (git_path / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            reference = head.split(":", 1)[1].strip()
            ref_path = git_path / reference
            if ref_path.is_file():
                return ref_path.read_text(encoding="utf-8").strip()[:128] or None
            packed = git_path / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    fields = line.strip().split(" ", 1)
                    if len(fields) == 2 and fields[1] == reference:
                        return fields[0][:128] or None
            return None
        return head[:128] or None
    except (OSError, UnicodeError):
        return None


def optional_file_hash(path: Path) -> str | None:
    try:
        return file_hash(path) if path.is_file() else None
    except OSError:
        return None


def project_fingerprint(root: Path) -> dict[str, Any]:
    """Return a bounded aggregate fingerprint for project files likely to affect work."""
    root = root.resolve()
    entries: list[str] = []
    file_count = 0
    total_bytes = 0
    truncated = False
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in PROJECT_SCAN_EXCLUDED_DIRS)
        for name in sorted(names):
            path = Path(current) / name
            if name not in PROJECT_SCAN_NAMES and path.suffix.lower() not in PROJECT_SCAN_SUFFIXES:
                continue
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
                relative = path.relative_to(root).as_posix()
                if (
                    file_count >= PROJECT_SCAN_MAX_FILES
                    or total_bytes + min(size, PROJECT_SCAN_MAX_FILE_BYTES) > PROJECT_SCAN_MAX_BYTES
                ):
                    truncated = True
                    break
                with path.open("rb") as handle:
                    if size <= PROJECT_SCAN_MAX_FILE_BYTES:
                        content = handle.read()
                    else:
                        head = handle.read(PROJECT_SCAN_MAX_FILE_BYTES // 2)
                        handle.seek(max(0, size - PROJECT_SCAN_MAX_FILE_BYTES // 2))
                        content = head + handle.read(PROJECT_SCAN_MAX_FILE_BYTES // 2)
                digest = hashlib.sha256(content).hexdigest()
                entries.append(f"{relative}\0{size}\0{digest}")
                file_count += 1
                total_bytes += min(size, PROJECT_SCAN_MAX_FILE_BYTES)
            except (OSError, UnicodeError, ValueError):
                truncated = True
        if truncated:
            break
    entries.sort()
    return {
        "version": 1,
        "digest": sha256_text("\n".join(entries)),
        "file_count": file_count,
        "total_bytes": total_bytes,
        "truncated": truncated,
    }


def _heading_references(text: str, section: str | None = None, maximum: int = MAX_REFERENCE_ITEMS) -> list[str]:
    body = text
    if section:
        body = requirements_section(text, section)
    references: list[str] = []
    for line in body.splitlines():
        match = re.match(r"^###\s+(.+?)\s*$", line)
        if match:
            references.append(match.group(1).strip())
    return references[-maximum:]


def _receipt_time(value: str, *, end_of_day: bool = False) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text + "T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if end_of_day and "T" not in text:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return parsed.astimezone(timezone.utc)


def research_receipts(context_dir: Path, maximum: int = MAX_REFERENCE_ITEMS) -> list[dict[str, Any]]:
    """Read compact receipts and mark whether they are safe for automatic reuse."""
    path = context_dir / "findings.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    chunks = re.split(r"(?m)(?=^###\s+)", text)
    receipts: list[dict[str, str]] = []
    for chunk in chunks:
        if not re.search(r"(?mi)^-\s*research_id:\s*\S+", chunk):
            continue
        item: dict[str, str] = {}
        for key in (
            "research_id",
            "question",
            "scope",
            "status",
            "sources",
            "question_hash",
            "scope_hash",
            "sources_fingerprint",
            "source_fingerprint",
            "conclusion",
            "decision_ref",
            "checked_at",
            "valid_until",
            "superseded_by",
        ):
            match = re.search(rf"(?mi)^-\s*{re.escape(key)}:\s*(.+)$", chunk)
            if match:
                item[key] = compact_text(match.group(1).strip(), 240)
        if item.get("research_id"):
            item["status"] = item.get("status", "UNKNOWN").upper()
            if item["status"] not in RESEARCH_RECEIPT_STATUSES:
                item["status"] = "UNKNOWN"
            validation_errors: list[str] = []
            if not item.get("question"):
                validation_errors.append("question missing")
            elif item.get("question_hash") != sha256_text(item["question"]):
                validation_errors.append("question_hash missing or mismatched")
            if not item.get("scope"):
                validation_errors.append("scope missing")
            elif item.get("scope_hash") != sha256_text(item["scope"]):
                validation_errors.append("scope_hash missing or mismatched")
            if not item.get("sources"):
                validation_errors.append("sources missing")
            elif (item.get("sources_fingerprint") or item.get("source_fingerprint")) != sha256_text(item["sources"]):
                validation_errors.append("sources_fingerprint missing or mismatched")
            if not item.get("conclusion"):
                validation_errors.append("conclusion missing")
            checked_at = _receipt_time(item.get("checked_at", ""))
            if checked_at is None:
                validation_errors.append("checked_at invalid")
            valid_until = _receipt_time(item.get("valid_until", ""), end_of_day=True)
            if item["status"] == "VALID" and valid_until is None:
                validation_errors.append("valid_until required for VALID receipt")
            if item.get("valid_until") and valid_until is None:
                validation_errors.append("valid_until invalid")
            validation_status = item["status"]
            if validation_errors:
                validation_status = "INCOMPLETE"
            elif item["status"] == "VALID" and valid_until and valid_until < datetime.now(timezone.utc):
                validation_status = "EXPIRED"
            item["validation_status"] = validation_status
            item["validation_errors"] = "; ".join(validation_errors)
            item["reusable"] = bool(validation_status == "VALID")
            receipts.append(item)
    # A duplicate id or one question with incompatible conclusions is a conflict,
    # regardless of which receipt was written most recently.
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_question: dict[str, list[dict[str, Any]]] = {}
    for item in receipts:
        by_id.setdefault(str(item.get("research_id")), []).append(item)
        key = str(item.get("question_hash") or sha256_text(str(item.get("question", ""))))
        by_question.setdefault(key, []).append(item)
    for group in by_id.values():
        if len(group) > 1:
            for item in group:
                item["validation_status"] = "CONFLICTED"
                item["validation_errors"] = "duplicate research_id"
                item["reusable"] = False
    for group in by_question.values():
        conclusions = {str(item.get("conclusion", "")).strip() for item in group}
        if len(group) > 1 and (len(conclusions) > 1 or len({str(item.get("scope", "")) for item in group}) > 1):
            for item in group:
                item["validation_status"] = "CONFLICTED"
                item["validation_errors"] = "duplicate id or conflicting conclusion/scope"
                item["reusable"] = False
    return receipts[-maximum:]


def continuity_baseline(root: Path, context_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    navigation = plan_navigation_view(root)
    return {
        "git_revision": git_revision(root),
        "plans_hash": optional_file_hash(root / "PLANS.md"),
        "project_fingerprint": project_fingerprint(root),
        "requirements_hash": manifest.get("recorded_requirements_hash"),
        "requirements_revision": requirements_revision(manifest),
        "task_id": manifest.get("task_id"),
        "current_task": manifest.get("task"),
        "route_coordinate": navigation.get("current_route_coordinate") if navigation.get("valid") else None,
        "checkpoint": manifest.get("checkpoint"),
    }


def continuity_snapshot(root: Path, context_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    current = continuity_baseline(root, context_dir, manifest)
    recorded = manifest.get("continuity_baseline")
    if not isinstance(recorded, dict) or not recorded:
        baseline_status = "UNKNOWN"
        changed_fields: list[str] = []
    else:
        compared = ("git_revision", "plans_hash", "project_fingerprint", "requirements_hash", "requirements_revision")
        changed_fields = [name for name in compared if recorded.get(name) != current.get(name)]
        baseline_status = "CHANGED" if changed_fields else "UNCHANGED"
    decisions = _heading_references((context_dir / "decisions.md").read_text(encoding="utf-8"), maximum=MAX_REFERENCE_ITEMS)
    findings = _heading_references((context_dir / "findings.md").read_text(encoding="utf-8"), section="Verified", maximum=MAX_REFERENCE_ITEMS)
    unknowns = _heading_references((context_dir / "findings.md").read_text(encoding="utf-8"), section="Open", maximum=MAX_REFERENCE_ITEMS)
    receipts = research_receipts(context_dir)
    return {
        "status": "FOUND",
        "baseline_status": baseline_status,
        "changed_fields": changed_fields,
        "current": current,
        "recorded": recorded if isinstance(recorded, dict) else {},
        "confirmed_decision_refs": decisions,
        "verified_finding_refs": findings,
        "open_unknowns": unknowns,
        "research_receipt_refs": [item.get("research_id") for item in receipts if item.get("research_id")],
        "reusable_research_receipt_refs": [
            item.get("research_id") for item in receipts if item.get("reusable") and item.get("research_id")
        ],
        "research_receipts": receipts,
        "recovery_tier": 0,
        "searched_scope": ["current-ledger", "verified-project"],
        "budget_used": {"max_chars": 0, "history_included": False},
        "blocking": bool(changed_fields),
        "next_action": (
            "Reconcile changed baseline fields before editing."
            if changed_fields
            else "Continue from the current checkpoint; retrieve history only for a specific unresolved question."
        ),
    }


def continuity_index(root: Path, context_dir: Path, manifest: dict[str, Any], next_action: str) -> dict[str, Any]:
    snapshot = continuity_snapshot(root, context_dir, manifest)
    return {
        "current_task": manifest.get("task"),
        "route_coordinate": snapshot["current"].get("route_coordinate"),
        "checkpoint": snapshot["current"].get("checkpoint"),
        "confirmed_decision_refs": snapshot["confirmed_decision_refs"],
        "verified_finding_refs": snapshot["verified_finding_refs"],
        "open_unknowns": snapshot["open_unknowns"],
        "research_receipt_refs": snapshot["research_receipt_refs"],
        "reusable_research_receipt_refs": snapshot["reusable_research_receipt_refs"],
        "next_action": compact_text(next_action, 600),
    }


def validate_unique_sections(sections: list[tuple[str, str]]) -> None:
    seen: set[str] = set()
    for name, _ in sections:
        if name in seen:
            raise ValueError(f"requirements contains duplicate section: {name}")
        seen.add(name)


def normalize_requirements(text: str, revision: int) -> str:
    value = require_requirements(text)
    if not value.startswith("# Current Requirements"):
        value = "# Current Requirements\n\n" + value
    preamble, sections = markdown_sections(value)
    validate_unique_sections(sections)
    kept = [(name, body) for name, body in sections if name not in {"Revision Log", "Current Revision"}]
    lines = [preamble or "# Current Requirements", ""]
    for name, body in kept:
        lines.extend((f"## {name}", body, ""))
    lines.extend(("## Current Revision", str(revision), ""))
    return "\n".join(lines).rstrip() + "\n"


def requirements_document_revision(text: str) -> int | None:
    _, sections = markdown_sections(text)
    for name, body in sections:
        if name == "Current Revision":
            first = body.splitlines()[0].strip() if body.strip() else ""
            return int(first) if first.isdigit() else None
    return None


def compact_text(value: str, maximum: int) -> str:
    text = value.strip()
    if len(text) <= maximum:
        return text
    marker = "\n...\n"
    if maximum <= len(marker):
        return text[:maximum]
    payload = maximum - len(marker)
    head = max(1, payload // 2)
    tail = max(1, payload - head)
    return text[:head].rstrip() + marker + text[-tail:].lstrip()


def requirements_brief_text(text: str, maximum: int) -> str:
    preamble, sections = markdown_sections(text)
    validate_unique_sections(sections)
    by_name = {name: body for name, body in sections}
    priorities = (
        ("Objective", 0.18),
        ("Current Route", 0.34),
        ("Current Revision", 0.08),
        ("Acceptance Standard", 0.20),
        ("Current Details", 0.15),
        ("Current Constraints", 0.05),
        ("Constraints", 0.05),
    )
    ordered = [(name, by_name[name], weight) for name, weight in priorities if name in by_name]
    if not ordered:
        return compact_text(text, maximum)
    title = preamble or "# Current Requirements"
    headings = [f"\n\n## {name}\n" for name, _, _ in ordered]
    available = maximum - len(title) - sum(len(heading) for heading in headings)
    if available <= 0:
        return title[:maximum]
    total_weight = sum(weight for _, _, weight in ordered) or 1.0
    budgets = [int(available * weight / total_weight) for _, _, weight in ordered]
    budgets[-1] += available - sum(budgets)
    output = [title]
    for heading, (_, body, _), budget in zip(headings, ordered, budgets):
        output.extend((heading, compact_text(body, max(0, budget))))
    return "".join(output)


def requirements_brief(path: Path, maximum: int) -> str:
    return requirements_brief_text(path.read_text(encoding="utf-8"), maximum)


def resolve_context_dir(root_arg: str, directory: str) -> tuple[Path, Path]:
    root = Path(root_arg).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"root is not a directory: {root}")

    requested = Path(directory)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("--dir must be a relative path within --root")

    context_dir = (root / requested).resolve()
    try:
        context_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("context directory must stay within --root") from exc
    return root, context_dir


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_name = handle.name
    os.replace(temp_name, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def change_event_hash(payload: dict[str, Any]) -> str:
    value = dict(payload)
    value.pop("event_hash", None)
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def rehash_change_log(context_dir: Path) -> None:
    path = context_dir / "changes.jsonl"
    if not path.is_file():
        return
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("changes.jsonl entries must be objects")
        values.append(value)
    has_requirement_changes = any(value.get("kind") == "requirement_change" for value in values)
    current_requirements = (context_dir / "requirements.md").read_text(encoding="utf-8")
    previous_hash = ""
    output: list[str] = []
    for value in values:
        if value.get("kind") == "task_started" and not isinstance(value.get("requirements_after"), str):
            if has_requirement_changes:
                value["legacy_snapshot_unavailable"] = True
            else:
                value["requirements_after"] = current_requirements
                value["requirements_hash"] = sha256_text(current_requirements)
        if value.get("kind") == "requirement_change" and not isinstance(value.get("requirements_after"), str):
            value["legacy_snapshot_unavailable"] = True
        value["previous_event_hash"] = previous_hash
        value["event_hash"] = change_event_hash(value)
        previous_hash = value["event_hash"]
        output.append(json.dumps(value, ensure_ascii=True, separators=(",", ":")))
    atomic_write(path, "\n".join(output) + ("\n" if output else ""))


@contextmanager
def ledger_lock(context_dir: Path):
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / ".ledger.lock"
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def wait_for_ledger_idle(context_dir: Path) -> None:
    with ledger_lock(context_dir):
        return


@contextmanager
def ledger_transaction(context_dir: Path, kind: str):
    transaction_path = context_dir / ".transaction.json"
    with ledger_lock(context_dir):
        if transaction_path.exists():
            raise ValueError(f"incomplete ledger transaction exists: {transaction_path}")
        backups = {
            name: (context_dir / name).read_text(encoding="utf-8") if (context_dir / name).is_file() else None
            for name in REQUIRED_FILES
        }
        transaction = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "started_at": utc_now(),
            "backups": backups,
        }
        atomic_write(
            transaction_path,
            json.dumps(transaction, ensure_ascii=True, indent=2) + "\n",
        )
        try:
            yield
        except Exception:
            for name, content in backups.items():
                path = context_dir / name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, content)
            transaction_path.unlink(missing_ok=True)
            raise
        else:
            transaction_path.unlink(missing_ok=True)


def recover_transaction(context_dir: Path) -> dict[str, Any]:
    transaction_path = context_dir / ".transaction.json"
    if not transaction_path.is_file():
        raise ValueError("no incomplete ledger transaction exists")
    removed_context = False
    with ledger_lock(context_dir):
        transaction = json.loads(transaction_path.read_text(encoding="utf-8"))
        backups = transaction.get("backups")
        if not isinstance(backups, dict):
            raise ValueError("transaction does not contain rollback backups")
        for name, content in backups.items():
            if name not in REQUIRED_FILES:
                continue
            path = context_dir / name
            if content is None:
                path.unlink(missing_ok=True)
            elif isinstance(content, str):
                atomic_write(path, content)
            else:
                raise ValueError(f"invalid transaction backup for {name}")
        transaction_path.unlink(missing_ok=True)
        kind = str(transaction.get("kind", "unknown"))
    if kind == "initialize" and not (context_dir / "manifest.json").exists():
        lock_path = context_dir / ".ledger.lock"
        lock_path.unlink(missing_ok=True)
        shutil.rmtree(context_dir)
        removed_context = True
    return {
        "transaction_id": transaction.get("id", "unknown"),
        "kind": kind,
        "restored": True,
        "removed_incomplete_context": removed_context,
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("manifest must contain a JSON object")
    return value


def write_manifest(context_dir: Path, manifest: dict[str, Any]) -> None:
    atomic_write(context_dir / "manifest.json", json.dumps(manifest, ensure_ascii=True, indent=2) + "\n")


def render_handoff(manifest: dict[str, Any], summary: str, next_action: str, verified: str, risks: str) -> str:
    baseline = manifest.get("continuity_baseline")
    baseline = baseline if isinstance(baseline, dict) else {}
    index = manifest.get("continuity_index")
    index = index if isinstance(index, dict) else {}
    return "\n".join(
        (
            "# Resume Brief",
            "",
            "## Objective",
            str(manifest["task"]),
            "",
            "## Current State",
            f"- Status: {manifest['status']}",
            f"- Checkpoint: {manifest['checkpoint']}",
            f"- Requirements revision: {requirements_revision(manifest)}",
            f"- Requirements hash: {manifest.get('recorded_requirements_hash', '')}",
            f"- Task root: {manifest.get('root', '')}",
            f"- Task ID: {manifest.get('task_id', '')}",
            f"- Updated: {manifest['updated_at']}",
            "",
            "## CONTINUITY STATUS",
            f"- Baseline status: {manifest.get('continuity_status', 'UNKNOWN')}",
            f"- Git revision: {baseline.get('git_revision') or 'UNKNOWN'}",
            f"- PLANS hash: {baseline.get('plans_hash') or 'NOT_CONFIGURED'}",
            f"- Project fingerprint: {str((baseline.get('project_fingerprint') or {}).get('digest', ''))[:16] or 'UNKNOWN'}",
            f"- Requirements hash: {baseline.get('requirements_hash') or manifest.get('recorded_requirements_hash', '')}",
            f"- Route coordinate: {index.get('route_coordinate') or 'NONE'}",
            f"- Confirmed decision refs: {json.dumps(index.get('confirmed_decision_refs', []), ensure_ascii=False)}",
            f"- Verified finding refs: {json.dumps(index.get('verified_finding_refs', []), ensure_ascii=False)}",
            f"- Open unknowns: {json.dumps(index.get('open_unknowns', []), ensure_ascii=False)}",
            f"- Research receipt refs: {json.dumps(index.get('research_receipt_refs', []), ensure_ascii=False)}",
            f"- Reusable receipt refs: {json.dumps(index.get('reusable_research_receipt_refs', []), ensure_ascii=False)}",
            "",
            "## Last Verified Progress",
            summary,
            "",
            "## Verification",
            verified or "Not provided. Recheck before relying on this state.",
            "",
            "## Next Action",
            next_action,
            "",
            "## Risks Or Blockers",
            risks or "None recorded.",
            "",
            "## Resume Protocol",
            "The next Codex turn should automatically validate this ledger and read this brief before acting.",
            "Check the current requirements revision and recent change log before relying on older decisions.",
            "Recheck current files, git state, tests, and external state before acting.",
            "Do not replay an action whose completion is uncertain.",
            "",
        )
    )


def initial_task(task: str) -> str:
    return "\n".join(
        (
            "# Task Execution",
            "",
            "## Requirements Reference",
            "Use `requirements.md` as the only source for objective, acceptance, route, constraints, and implementation details.",
            "",
            "## Execution Plan",
            "- [ ] Inspect current state and identify the first concrete phase.",
            "",
            "## Execution Notes",
            "- Task execution notes are non-authoritative and must not redefine requirements.",
            "",
        )
    )


def requirements_objective(text: str) -> str:
    _, sections = markdown_sections(text)
    validate_unique_sections(sections)
    for name, body in sections:
        if name == "Objective":
            return body.strip()
    return ""


def requirements_section(text: str, section_name: str) -> str:
    _, sections = markdown_sections(text)
    validate_unique_sections(sections)
    for name, body in sections:
        if name == section_name:
            return body
    return ""


def merge_current_detail(current: str, summary: str, impact: str) -> str:
    preamble, sections = markdown_sections(current)
    validate_unique_sections(sections)
    summary = require_text(summary, "detail summary")
    impact = impact.strip()
    if "\n" in summary or "\r" in summary or re.search(r"(?m)^\s*##\s+", summary):
        raise ValueError("detail summary must be a single line without Markdown headings")
    if "\n" in impact or "\r" in impact or re.search(r"(?m)^\s*##\s+", impact):
        raise ValueError("detail impact must be a single line without Markdown headings")
    updated: list[tuple[str, str]] = []
    detail_line = f"- {summary}"
    if impact.strip():
        detail_line += f" Impact: {impact}"
    detail_key = detail_line[2:].split(":", 1)[0].strip().casefold() if ":" in detail_line else ""
    found = False
    for name, body in sections:
        if name in {"Revision Log", "Current Revision"}:
            continue
        if name == "Current Details":
            found = True
            lines = body.splitlines() if body.strip() else []
            replaced = False
            next_lines: list[str] = []
            for line in lines:
                existing = line.strip()[2:].strip() if line.strip().startswith("- ") else ""
                existing_key = existing.split(":", 1)[0].strip().casefold() if ":" in existing else ""
                if detail_key and existing_key == detail_key:
                    if not replaced:
                        next_lines.append(detail_line)
                        replaced = True
                    continue
                next_lines.append(line)
            if not replaced and detail_line not in next_lines:
                next_lines.append(detail_line)
            lines = next_lines
            updated.append((name, "\n".join(lines)))
        else:
            updated.append((name, body))
    if not found:
        updated.append(("Current Details", detail_line))
    lines = [preamble or "# Current Requirements", ""]
    for name, body in updated:
        lines.extend((f"## {name}", body, ""))
    return "\n".join(lines).rstrip() + "\n"


def normalize_task_execution(text: str) -> str:
    _, sections = markdown_sections(text)
    by_name = {name: body for name, body in sections}
    plan = by_name.get("Execution Plan") or by_name.get("Plan") or "- [ ] Inspect current state and identify the next phase."
    notes = by_name.get("Execution Notes", "- Migrated from an earlier task ledger.")
    return "\n".join(
        (
            "# Task Execution",
            "",
            "## Requirements Reference",
            "Use `requirements.md` as the only source for objective, acceptance, route, constraints, and implementation details.",
            "",
            "## Execution Plan",
            plan,
            "",
            "## Execution Notes",
            notes,
            "",
        )
    )


def task_execution_brief(path: Path, maximum: int) -> str:
    text = path.read_text(encoding="utf-8")
    _, sections = markdown_sections(text)
    by_name = {name: body for name, body in sections}
    plan = by_name.get("Execution Plan", "No execution plan recorded.")
    return compact_text(
        "# Task Execution\n\nNon-authoritative execution sequence; `requirements.md` overrides any conflict.\n\n"
        "## Execution Plan\n"
        + plan,
        maximum,
    )


def initialize(root: Path, context_dir: Path, task: str) -> None:
    if context_dir.exists():
        raise ValueError(f"context directory already exists: {context_dir}")
    context_dir.mkdir(parents=True)
    task = require_task(task)
    now = utc_now()
    requirements = normalize_requirements(initial_requirements(task), 0)
    start_id = uuid.uuid4().hex
    manifest = {
        "version": LEDGER_VERSION,
        "task_id": uuid.uuid4().hex,
        "task": task,
        "status": "active",
        "checkpoint": 0,
        "requirements_revision": 0,
        "last_change_id": start_id,
        "last_event_id": start_id,
        "recorded_requirements_hash": sha256_text(requirements),
        "checkpoint_hashes": {},
        "continuity_baseline": {},
        "continuity_index": {},
        "continuity_status": "UNKNOWN",
        "created_at": now,
        "updated_at": now,
        "root": str(root),
    }
    with ledger_transaction(context_dir, "initialize"):
        write_manifest(context_dir, manifest)
        atomic_write(context_dir / "task.md", initial_task(task))
        atomic_write(context_dir / "requirements.md", requirements)
        atomic_write(context_dir / "findings.md", "# Findings\n\n## Verified\n\n")
        atomic_write(context_dir / "decisions.md", "# Decisions\n\n## Decision Log\n\n")
        atomic_write(context_dir / "changes.jsonl", "")
        manifest["continuity_baseline"] = continuity_baseline(root, context_dir, manifest)
        manifest["continuity_status"] = "UNCHANGED"
        manifest["continuity_index"] = continuity_index(
            root,
            context_dir,
            manifest,
            "Identify the first concrete phase and update task.md.",
        )
        atomic_write(
            context_dir / "handoff.md",
            render_handoff(
                manifest,
                "Ledger initialized. Inspect the repository before recording findings.",
                "Identify the first concrete phase and update task.md.",
                "Not yet verified.",
                "No repository state has been inspected yet.",
            ),
        )
        append_jsonl(context_dir / "history.jsonl", {"at": now, "kind": "init", "task": task})
        append_change(
            context_dir,
            {
                "id": start_id,
                "at": now,
                "kind": "task_started",
                "category": "scope",
                "summary": "Initial task requirements created.",
                "source": "user_task",
                "revision": 0,
                "requirements_after": requirements,
                "requirements_hash": sha256_text(requirements),
            },
        )
        manifest["checkpoint_hashes"] = content_hashes(context_dir)
        write_manifest(context_dir, manifest)


def migrate_ledger(context_dir: Path, expected_root: Path | None = None) -> None:
    """Add the versioned requirement and change ledger to an older context directory."""
    if not context_dir.is_dir():
        return
    wait_for_ledger_idle(context_dir)
    if (context_dir / ".transaction.json").exists():
        raise ValueError(f"incomplete ledger transaction exists: {context_dir / '.transaction.json'}")
    manifest = read_json(context_dir / "manifest.json")
    expected_root = expected_root.resolve() if expected_root else None
    changed = False
    now = utc_now()
    task = str(manifest.get("task", "Unspecified task"))
    if expected_root and manifest.get("root"):
        recorded_root = canonical_path(manifest.get("root"), "manifest root")
        if recorded_root != expected_root:
            raise ValueError(f"ledger belongs to a different project root: {recorded_root}")
    if not manifest.get("root"):
        if not expected_root:
            raise ValueError("legacy ledger is missing its project root")
        manifest["root"] = str(expected_root)
        changed = True
    task_id = str(manifest.get("task_id", "")).strip()
    if not TASK_ID_PATTERN.fullmatch(task_id):
        manifest["task_id"] = uuid.uuid4().hex
        changed = True
    if not (context_dir / "requirements.md").is_file():
        atomic_write(context_dir / "requirements.md", initial_requirements(task))
        changed = True
    if not (context_dir / "changes.jsonl").is_file():
        atomic_write(context_dir / "changes.jsonl", "")
        append_change(
            context_dir,
            {
                "id": uuid.uuid4().hex,
                "at": now,
                "kind": "ledger_migrated",
                "category": "system",
                "summary": "Added versioned requirements and change history.",
                "source": "durable-context-migration",
                "revision": 0,
            },
        )
        changed = True
    if manifest.get("version", 1) < LEDGER_VERSION:
        manifest["version"] = LEDGER_VERSION
        changed = True
    if "requirements_revision" not in manifest:
        manifest["requirements_revision"] = 0
        changed = True
    if "last_change_id" not in manifest:
        manifest["last_change_id"] = ""
        changed = True
    if "last_event_id" not in manifest:
        manifest["last_event_id"] = ""
        changed = True
    if "recorded_requirements_hash" not in manifest:
        manifest["recorded_requirements_hash"] = ""
        changed = True
    if "checkpoint_hashes" not in manifest:
        manifest["checkpoint_hashes"] = content_hashes(context_dir)
        changed = True
    if "continuity_baseline" not in manifest:
        manifest["continuity_baseline"] = {}
        changed = True
    if "continuity_index" not in manifest:
        manifest["continuity_index"] = {}
        changed = True
    if "continuity_status" not in manifest:
        manifest["continuity_status"] = "UNKNOWN"
        changed = True
    existing_changes = read_changes(context_dir, maximum=100000)
    if any(not entry.get("event_hash") for entry in existing_changes):
        changed = True
    if any(
        entry.get("kind") == "task_started" and not isinstance(entry.get("requirements_after"), str)
        for entry in existing_changes
    ):
        changed = True
    if changed:
        with ledger_transaction(context_dir, "migrate"):
            revision = requirements_revision(manifest)
            normalized = normalize_requirements((context_dir / "requirements.md").read_text(encoding="utf-8"), revision)
            objective = requirements_objective(normalized)
            if not objective:
                raise ValueError("requirements.md must contain a non-empty Objective section")
            atomic_write(context_dir / "requirements.md", normalized)
            atomic_write(
                context_dir / "task.md",
                normalize_task_execution((context_dir / "task.md").read_text(encoding="utf-8")),
            )
            rehash_change_log(context_dir)
            entries = read_changes(context_dir, maximum=100000)
            last_event = entries[-1] if entries else {}
            requirement_events = [
                entry
                for entry in entries
                if entry.get("kind") in {"task_started", "requirement_change"}
            ]
            last_requirement = requirement_events[-1] if requirement_events else {}
            manifest["last_event_id"] = str(last_event.get("id", ""))
            manifest["last_change_id"] = str(last_requirement.get("id", ""))
            manifest["task"] = objective
            manifest["recorded_requirements_hash"] = file_hash(context_dir / "requirements.md")
            manifest["checkpoint_hashes"] = content_hashes(context_dir)
            manifest["continuity_baseline"] = continuity_baseline(expected_root or context_dir.parent, context_dir, manifest)
            manifest["continuity_status"] = "UNCHANGED"
            manifest["continuity_index"] = continuity_index(
                expected_root or context_dir.parent,
                context_dir,
                manifest,
                "Validate the current project and continue from the latest verified checkpoint.",
            )
            manifest["updated_at"] = now
            handoff_path = context_dir / "handoff.md"
            handoff_text = handoff_path.read_text(encoding="utf-8") if handoff_path.is_file() else ""
            atomic_write(
                handoff_path,
                render_handoff(
                    manifest,
                    "Legacy ledger metadata migrated. Re-check current files before relying on this state.",
                    "Validate the current project and continue from the latest verified checkpoint.",
                    "Ledger migration completed; implementation evidence must be rechecked.",
                    "The previous handoff was retained only as migration input and is no longer authoritative."
                    if handoff_text.strip()
                    else "No prior handoff was available.",
                ),
            )
            manifest["checkpoint_hashes"] = content_hashes(context_dir)
            write_manifest(context_dir, manifest)


def archive_completed(
    root: Path,
    context_dir: Path,
    manifest: dict[str, Any],
    reason: str = "new_task_after_completed_task",
) -> Path:
    archive_root = root / ".agent-context-archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    task_id = validate_task_id(manifest.get("task_id"))
    destination = archive_root / task_id
    suffix = 1
    while destination.exists():
        destination = archive_root / f"{task_id}-{suffix}"
        suffix += 1
    try:
        destination.resolve().relative_to(archive_root.resolve())
    except ValueError as exc:
        raise ValueError("archive destination escapes the project archive root") from exc
    transaction_path = context_dir / ".transaction.json"
    with ledger_lock(context_dir):
        if transaction_path.exists():
            raise ValueError(f"incomplete ledger transaction exists: {transaction_path}")
        atomic_write(
            transaction_path,
            json.dumps(
                {
                    "id": uuid.uuid4().hex,
                    "kind": "archive",
                    "started_at": utc_now(),
                    "backups": {},
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
        )
    try:
        shutil.move(str(context_dir), str(destination))
    except Exception:
        transaction_path.unlink(missing_ok=True)
        raise
    (destination / ".transaction.json").unlink(missing_ok=True)
    append_jsonl(
        archive_root / "index.jsonl",
        {
            "at": utc_now(),
            "task_id": task_id,
            "task": manifest.get("task", ""),
            "archived_to": str(destination),
            "reason": reason,
        },
    )
    return destination


def checkpoint(
    context_dir: Path,
    summary: str,
    next_action: str,
    verified: str,
    risks: str,
    status: str,
    expected_root: Path | None = None,
) -> None:
    with ledger_transaction(context_dir, "checkpoint"):
        manifest = read_json(context_dir / "manifest.json")
        current_requirements_hash = file_hash(context_dir / "requirements.md")
        if current_requirements_hash != manifest.get("recorded_requirements_hash"):
            raise ValueError("unrecorded requirements change; record a requirement change before checkpointing")
        if status == "complete":
            if not verified.strip():
                raise ValueError("complete checkpoint requires non-empty verification evidence")
            acceptance = requirements_section(
                (context_dir / "requirements.md").read_text(encoding="utf-8"),
                "Acceptance Standard",
            )
            if re.search(r"(?m)^\s*- \[ \]", acceptance):
                raise ValueError("cannot complete while Acceptance Standard has unfinished items")
        pre_errors = verify(context_dir, ignore_transaction=True, expected_root=expected_root)
        if status != "complete":
            pre_errors = [
                error
                for error in pre_errors
                if error
                not in {
                    "complete ledger must contain verification evidence in handoff",
                    "complete ledger has unfinished Acceptance Standard items",
                }
            ]
        if pre_errors:
            raise ValueError("ledger is invalid before checkpoint: " + "; ".join(pre_errors))
        manifest["checkpoint"] = int(manifest.get("checkpoint", 0)) + 1
        manifest["status"] = status
        manifest["updated_at"] = utc_now()
        root = expected_root.resolve() if expected_root else context_dir.parent.resolve()
        manifest["continuity_baseline"] = continuity_baseline(root, context_dir, manifest)
        manifest["continuity_status"] = "UNCHANGED"
        manifest["continuity_index"] = continuity_index(root, context_dir, manifest, next_action)
        write_manifest(context_dir, manifest)
        atomic_write(context_dir / "handoff.md", render_handoff(manifest, summary, next_action, verified, risks))
        append_jsonl(
            context_dir / "history.jsonl",
            {
                "at": manifest["updated_at"],
                "kind": "checkpoint",
                "number": manifest["checkpoint"],
                "status": status,
                "summary": summary,
                "next_action": next_action,
                "verified": verified,
                "risks": risks,
            },
        )
        event = append_change(
            context_dir,
            {
                "id": uuid.uuid4().hex,
                "at": manifest["updated_at"],
                "kind": "checkpoint",
                "checkpoint": manifest["checkpoint"],
                "revision": requirements_revision(manifest),
                "summary": summary,
                "status": status,
            },
        )
        manifest["last_event_id"] = event["id"]
        manifest["checkpoint_hashes"] = content_hashes(context_dir)
        write_manifest(context_dir, manifest)


def read_changes(context_dir: Path, maximum: int = 20) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    path = context_dir / "changes.jsonl"
    if not path.is_file():
        return entries
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            entries.append({"kind": "invalid", "line": number})
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries[-maximum:]


def strict_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    """Read an audit projection without silently skipping malformed records."""
    entries: list[dict[str, Any]] = []
    if not path.is_file():
        return entries
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} has invalid JSON on line {number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{label} entry on line {number} must be an object")
        entries.append(value)
    return entries


def trusted_change_projection(context_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the append-only change projection before rebuilding derived files."""
    entries = strict_jsonl(context_dir / "changes.jsonl", "changes.jsonl")
    previous_hash = ""
    seen_ids: set[str] = set()
    revision = 0
    requirement_hash = ""
    checkpoints: list[int] = []
    for number, entry in enumerate(entries, start=1):
        event_id = str(entry.get("id", ""))
        if not event_id or event_id in seen_ids:
            raise ValueError(f"changes.jsonl has an invalid or duplicate id on line {number}")
        seen_ids.add(event_id)
        if entry.get("previous_event_hash", "") != previous_hash:
            raise ValueError(f"changes.jsonl hash chain is broken on line {number}")
        if entry.get("event_hash") != change_event_hash(entry):
            raise ValueError(f"changes.jsonl event hash is invalid on line {number}")
        previous_hash = str(entry["event_hash"])
        kind = entry.get("kind")
        if kind == "task_started":
            if entry.get("revision") != 0:
                raise ValueError(f"task_started revision is invalid on line {number}")
            snapshot = entry.get("requirements_after")
            if not isinstance(snapshot, str) or entry.get("requirements_hash") != sha256_text(snapshot):
                raise ValueError(f"task_started requirements snapshot is invalid on line {number}")
            requirement_hash = str(entry["requirements_hash"])
        elif kind == "requirement_change":
            before = entry.get("before_revision")
            after = entry.get("after_revision")
            if before != revision or not isinstance(after, int) or after != revision + 1:
                raise ValueError(f"requirement revision chain is broken on line {number}")
            snapshot = entry.get("requirements_after")
            if not isinstance(snapshot, str) or entry.get("requirements_hash") != sha256_text(snapshot):
                raise ValueError(f"requirement snapshot is invalid on line {number}")
            revision = after
            requirement_hash = str(entry["requirements_hash"])
        elif kind == "checkpoint":
            number_value = entry.get("checkpoint")
            if not isinstance(number_value, int) or number_value <= 0:
                raise ValueError(f"checkpoint projection is invalid on line {number}")
            checkpoints.append(number_value)

    if revision != requirements_revision(manifest):
        raise ValueError("RECOVERY_REQUIRED: changes.jsonl requirements revision conflicts with manifest")
    if requirement_hash and requirement_hash != str(manifest.get("recorded_requirements_hash", "")):
        raise ValueError("RECOVERY_REQUIRED: changes.jsonl requirements hash conflicts with manifest")
    expected_checkpoints = list(range(1, len(checkpoints) + 1))
    if checkpoints != expected_checkpoints:
        raise ValueError("RECOVERY_REQUIRED: changes.jsonl checkpoint sequence is ambiguous")
    if len(checkpoints) != int(manifest.get("checkpoint", -1)):
        raise ValueError("RECOVERY_REQUIRED: changes.jsonl cannot prove the manifest checkpoint")
    return entries


def repair_ledger(root: Path, context_dir: Path) -> dict[str, Any]:
    """Repair only generated projections whose authoritative source is unambiguous."""
    if not context_dir.is_dir():
        raise ValueError("context directory does not exist")
    wait_for_ledger_idle(context_dir)
    if (context_dir / ".transaction.json").is_file():
        raise ValueError("RECOVERY_REQUIRED: incomplete ledger transaction must be recovered first")

    manifest = read_json(context_dir / "manifest.json")
    root = root.resolve()
    if canonical_path(manifest.get("root"), "manifest root") != root:
        raise ValueError("RECOVERY_REQUIRED: ledger belongs to a different project root")
    if file_hash(context_dir / "requirements.md") != manifest.get("recorded_requirements_hash"):
        raise ValueError("RECOVERY_REQUIRED: requirements.md is not an authorized projection")

    checkpoint_hashes = manifest.get("checkpoint_hashes")
    if not isinstance(checkpoint_hashes, dict):
        raise ValueError("RECOVERY_REQUIRED: checkpoint hashes are unavailable")
    current_hashes = content_hashes(context_dir)
    for name in ("task.md", "requirements.md", "findings.md", "decisions.md"):
        expected = checkpoint_hashes.get(name)
        if not expected or current_hashes.get(name) != expected:
            raise ValueError(f"RECOVERY_REQUIRED: authoritative ledger file drifted: {name}")

    baseline = continuity_snapshot(root, context_dir, manifest)

    changes = trusted_change_projection(context_dir, manifest)
    history = strict_jsonl(context_dir / "history.jsonl", "history.jsonl")
    history_checkpoints = [
        entry.get("number")
        for entry in history
        if entry.get("kind") == "checkpoint"
    ]
    expected_history = list(range(1, int(manifest.get("checkpoint", 0)) + 1))
    repaired: list[str] = []
    recovered_history_entry: dict[str, Any] | None = None

    if history_checkpoints != expected_history:
        if (
            len(history_checkpoints) >= len(expected_history)
            or history_checkpoints != expected_history[: len(history_checkpoints)]
            or any(entry.get("kind") not in {"init", "checkpoint"} for entry in history)
        ):
            raise ValueError("RECOVERY_REQUIRED: history.jsonl checkpoint projection is ambiguous")
        missing = expected_history[len(history_checkpoints) :]
        if len(missing) != 1:
            raise ValueError("RECOVERY_REQUIRED: more than one history checkpoint is missing")
        missing_number = missing[0]
        source = next(
            (entry for entry in changes if entry.get("kind") == "checkpoint" and entry.get("checkpoint") == missing_number),
            None,
        )
        if source is None:
            raise ValueError("RECOVERY_REQUIRED: missing checkpoint is not proven by changes.jsonl")
        recovered_history_entry = {
            "at": str(source.get("at") or utc_now()),
            "kind": "checkpoint",
            "number": missing_number,
            "status": str(source.get("status") or "active"),
            "summary": "Recovered checkpoint metadata from changes.jsonl; original detail was not preserved.",
            "next_action": "Verify current files before relying on this recovered checkpoint.",
            "verified": "Checkpoint existence is proven by the append-only changes log; detail requires revalidation.",
            "risks": "Recovered projection; do not treat its missing detail as historical fact.",
        }
        repaired.append(f"history.jsonl checkpoint {missing_number}")
        history = [*history, recovered_history_entry]

    latest = next(
        (entry for entry in reversed(history) if entry.get("kind") == "checkpoint"),
        None,
    )
    if int(manifest.get("checkpoint", 0)) and latest is None:
        raise ValueError("RECOVERY_REQUIRED: no trusted latest checkpoint is available")
    handoff_expected = checkpoint_hashes.get("handoff")
    handoff_drifted = bool(handoff_expected and current_hashes.get("handoff") != handoff_expected)
    rendered_handoff: str | None = None
    if handoff_drifted or recovered_history_entry is not None:
        if latest is None:
            summary = "Recovered generated handoff; no checkpoint detail is available."
            next_action = "Verify the current project before continuing."
            verified = "No checkpoint evidence was available; this handoff is a recovery marker only."
            risks = "Recovery marker requires explicit verification before relying on prior context."
        else:
            summary = str(latest.get("summary") or "Recovered generated handoff from the latest checkpoint.")
            next_action = str(latest.get("next_action") or "Verify the current project before continuing.")
            verified = str(latest.get("verified") or "Checkpoint detail was incomplete; revalidate before relying on it.")
            risks = str(latest.get("risks") or "Revalidate the recovered handoff before relying on it.")
        rendered_handoff = render_handoff(manifest, summary, next_action, verified, risks)
        if (context_dir / "handoff.md").read_text(encoding="utf-8") != rendered_handoff:
            repaired.append("handoff.md")

    if not repaired:
        errors = verify(context_dir, expected_root=root)
        if errors:
            raise ValueError("RECOVERY_REQUIRED: no safe projection repair applies: " + "; ".join(errors))
        return {
            "action": "already_valid",
            "repaired": [],
            "verified": True,
            "baseline_status": baseline.get("baseline_status", "UNKNOWN"),
            "rebaseline_required": baseline.get("baseline_status") == "CHANGED",
        }

    with ledger_transaction(context_dir, "repair"):
        if recovered_history_entry is not None:
            append_jsonl(context_dir / "history.jsonl", recovered_history_entry)
        if rendered_handoff is not None and "handoff.md" in repaired:
            atomic_write(context_dir / "handoff.md", rendered_handoff)
        now = utc_now()
        event = append_change(
            context_dir,
            {
                "id": uuid.uuid4().hex,
                "at": now,
                "kind": "repair",
                "category": "recovery",
                "summary": "Repaired generated ledger projections: " + ", ".join(repaired),
                "source": "durable-context-repair",
                "status": "repaired",
            },
        )
        manifest = read_json(context_dir / "manifest.json")
        manifest["last_event_id"] = event["id"]
        manifest["updated_at"] = now
        manifest["checkpoint_hashes"] = content_hashes(context_dir)
        write_manifest(context_dir, manifest)
        errors = verify(context_dir, ignore_transaction=True, expected_root=root)
        if errors:
            raise ValueError("RECOVERY_REQUIRED: repair verification failed: " + "; ".join(errors))
    return {
        "action": "repaired",
        "repaired": repaired,
        "verified": True,
        "baseline_status": baseline.get("baseline_status", "UNKNOWN"),
        "rebaseline_required": baseline.get("baseline_status") == "CHANGED",
    }


def compact_change_entries(entries: list[dict[str, Any]]) -> str:
    allowed = (
        "id",
        "at",
        "kind",
        "category",
        "summary",
        "impact",
        "source",
        "revision",
        "before_revision",
        "after_revision",
        "checkpoint",
        "status",
    )
    compact = [{key: entry[key] for key in allowed if key in entry} for entry in entries]
    return json.dumps(compact, ensure_ascii=False, indent=2)


def last_recorded_requirements(context_dir: Path) -> str:
    for entry in reversed(read_changes(context_dir, maximum=100000)):
        if entry.get("kind") in {"task_started", "requirement_change"}:
            snapshot = entry.get("requirements_after")
            if isinstance(snapshot, str):
                return snapshot
    raise ValueError("no trusted requirements snapshot exists in the change log")


def render_budgeted_resume(
    manifest: dict[str, Any],
    maximum: int,
    sections: list[tuple[str, str, float]],
) -> str:
    header = (
        "# Durable Context Resume\n\n"
        f"Task ID: {manifest.get('task_id', 'unknown')} | "
        f"Status: {manifest.get('status', 'unknown')} | "
        f"Requirements revision: {requirements_revision(manifest)}"
    )
    headings = [f"\n\n## {name}\n" for name, _, _ in sections]
    available = maximum - len(header) - sum(len(value) for value in headings)
    if available <= 0:
        return header[:maximum]
    total_weight = sum(weight for _, _, weight in sections) or 1.0
    budgets = [int(available * weight / total_weight) for _, _, weight in sections]
    budgets[-1] += available - sum(budgets)
    output = [header]
    for heading, (_, content, _), budget in zip(headings, sections, budgets):
        rendered_content = (
            requirements_brief_text(content, max(0, budget))
            if heading == "\n\n## Current Requirements\n"
            else compact_text(content, max(0, budget))
        )
        output.extend((heading, rendered_content))
    rendered = "".join(output)
    if len(rendered) > maximum:
        raise RuntimeError("resume renderer exceeded its character budget")
    return rendered


def change(
    context_dir: Path,
    summary: str,
    category: str,
    source: str,
    impact: str,
    requirements: str,
    expected_root: Path | None = None,
) -> dict[str, Any]:
    if category in {"route", "acceptance", "scope"} and not requirements.strip():
        raise ValueError("a current requirements snapshot is required for route, acceptance, or scope changes")
    manifest_before = read_json(context_dir / "manifest.json")
    if file_hash(context_dir / "requirements.md") != manifest_before.get("recorded_requirements_hash"):
        raise ValueError(
            "requirements.md contains an unrecorded change; reconcile the file before recording a new requirement change"
        )
    with ledger_transaction(context_dir, "requirement_change"):
        pre_errors = verify(context_dir, ignore_transaction=True, expected_root=expected_root)
        if pre_errors:
            raise ValueError("ledger is invalid before requirement change: " + "; ".join(pre_errors))
        manifest = read_json(context_dir / "manifest.json")
        previous_revision = requirements_revision(manifest)
        next_revision = previous_revision + 1
        current_file = (context_dir / "requirements.md").read_text(encoding="utf-8")
        current = (
            last_recorded_requirements(context_dir)
            if file_hash(context_dir / "requirements.md") != manifest.get("recorded_requirements_hash")
            else current_file
        )
        source_requirements = requirements if requirements.strip() else merge_current_detail(current, summary, impact)
        updated_requirements = normalize_requirements(source_requirements, next_revision)
        objective = requirements_objective(updated_requirements)
        if not objective:
            raise ValueError("requirements snapshot must contain a non-empty Objective section")
        now = utc_now()
        change_id = uuid.uuid4().hex
        payload = {
            "id": change_id,
            "at": now,
            "kind": "requirement_change",
            "category": category,
            "summary": summary,
            "impact": impact,
            "source": source,
            "before_revision": previous_revision,
            "after_revision": next_revision,
            "requirements_before": current,
            "requirements_after": updated_requirements,
            "requirements_hash": sha256_text(updated_requirements),
        }
        atomic_write(context_dir / "requirements.md", updated_requirements)
        enriched = append_change(context_dir, payload)
        manifest["requirements_revision"] = next_revision
        manifest["task"] = objective
        manifest["last_change_id"] = change_id
        manifest["last_event_id"] = change_id
        manifest["recorded_requirements_hash"] = sha256_text(updated_requirements)
        manifest["updated_at"] = now
        write_manifest(context_dir, manifest)
        atomic_write(
            context_dir / "handoff.md",
            render_handoff(
                manifest,
                summary,
                "Validate the revised requirements against current files before checkpointing.",
                "Requirement change recorded in the append-only change log.",
                impact.strip() or "Recheck acceptance, route, and implementation details before continuing.",
            ),
        )
        # A recorded requirement change is an authorized ledger lifecycle event.
        # Refresh its ledger hashes so the Hook does not mistake our own handoff
        # rewrite for external tampering, while project drift remains gated.
        root = expected_root.resolve() if expected_root else context_dir.parent.resolve()
        manifest["continuity_baseline"] = continuity_baseline(root, context_dir, manifest)
        manifest["continuity_status"] = "UNCHANGED"
        manifest["continuity_index"] = continuity_index(
            root,
            context_dir,
            manifest,
            "Validate the revised requirements against current files before checkpointing.",
        )
        manifest["checkpoint_hashes"] = content_hashes(context_dir)
        write_manifest(context_dir, manifest)
    return enriched


def reconcile(context_dir: Path, expected_root: Path | None = None) -> dict[str, Any]:
    errors = verify(context_dir, expected_root=expected_root)
    warnings: list[str] = []
    blocking_warnings: list[str] = []
    manifest = read_json(context_dir / "manifest.json") if not errors else {}
    checkpoint_hashes = manifest.get("checkpoint_hashes", {})
    current_hashes = content_hashes(context_dir)
    if isinstance(checkpoint_hashes, dict):
        for name, digest in current_hashes.items():
            expected = checkpoint_hashes.get(name)
            if expected and expected != digest:
                message = f"uncheckpointed content change: {name}"
                warnings.append(message)
                blocking_warnings.append(message)
            elif not expected:
                message = f"uncheckpointed content added: {name}"
                warnings.append(message)
                blocking_warnings.append(message)
    if manifest and current_hashes.get("requirements.md") != manifest.get("recorded_requirements_hash"):
        message = "unrecorded requirements change"
        warnings.append(message)
        blocking_warnings.append(message)

    changes = read_changes(context_dir, maximum=100000)
    revision_entries = [
        entry
        for entry in changes
        if entry.get("kind") == "requirement_change" and isinstance(entry.get("after_revision"), int)
    ]
    last_revision = revision_entries[-1]["after_revision"] if revision_entries else 0
    manifest_revision = requirements_revision(manifest) if manifest else 0
    if last_revision != manifest_revision:
        warnings.append(
            f"requirements revision mismatch: change log={last_revision}, manifest={manifest_revision}"
        )
    if not errors:
        requirements_text = (context_dir / "requirements.md").read_text(encoding="utf-8")
        document_revision = requirements_document_revision(requirements_text)
        if document_revision != manifest_revision:
            message = f"requirements document revision mismatch: document={document_revision}, manifest={manifest_revision}"
            warnings.append(message)
            blocking_warnings.append(message)

    baseline_status = "UNKNOWN"
    baseline_changed: list[str] = []
    if manifest and not errors:
        snapshot = continuity_snapshot(context_dir.parent, context_dir, manifest)
        baseline_status = str(snapshot.get("baseline_status", "UNKNOWN"))
        baseline_changed = list(snapshot.get("changed_fields", []))
        if baseline_changed:
            message = "baseline drift: " + ", ".join(baseline_changed)
            warnings.append(message)
            blocking_warnings.append(message)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "blocking_warnings": list(dict.fromkeys(blocking_warnings)),
        "blocking": bool(errors or blocking_warnings),
        "baseline_status": baseline_status,
        "baseline_changed": baseline_changed,
        "requirements_revision": manifest_revision,
        "recent_changes": read_changes(context_dir, maximum=8),
    }


def automatic(
    root: Path,
    context_dir: Path,
    event: str,
    task: str,
    summary: str,
    next_action: str,
    verified: str,
    risks: str,
    status: str,
    maximum: int,
    category: str = "",
    source: str = "",
    impact: str = "",
    requirements: str = "",
) -> dict[str, Any]:
    """Run the lifecycle through one internal, agent-facing routing entry point."""
    if event == "recover":
        if not context_dir.is_dir():
            raise ValueError("context directory does not exist")
        result = recover_transaction(context_dir)
        if result["removed_incomplete_context"] and task.strip():
            initialize(root, context_dir, require_task(task))
            result["reinitialized"] = True
        return {"action": "transaction_recovered", "context_dir": str(context_dir), **result}

    if event == "start":
        if context_dir.exists():
            wait_for_ledger_idle(context_dir)
            if (context_dir / ".transaction.json").exists():
                return {
                    "action": "recovery_required",
                    "context_dir": str(context_dir),
                    "transaction": json.loads((context_dir / ".transaction.json").read_text(encoding="utf-8")),
                }
            migrate_ledger(context_dir, root)
            existing = read_json(context_dir / "manifest.json")
            task_mismatch = task.strip() and task.strip() != str(existing.get("task", "")).strip()
            if task_mismatch:
                if existing.get("status") == "complete":
                    archive_completed(root, context_dir, existing)
                    initialize(root, context_dir, require_task(task))
                    return {
                        "action": "initialized_after_archive",
                        "context_dir": str(context_dir),
                        "resume": resume(context_dir, maximum),
                    }
                return {
                    "action": "objective_conflict",
                    "context_dir": str(context_dir),
                    "current_task": existing.get("task", ""),
                    "proposed_task": task.strip(),
                    "status": existing.get("status", "unknown"),
                    "resolution": "record a scope change for the same task, or use the internal switch event for a distinct task",
                    "consistency": reconcile(context_dir, root),
                }
            errors = verify(context_dir, expected_root=root)
            if errors:
                consistency = reconcile(context_dir, root)
                manifest = read_json(context_dir / "manifest.json")
                return {
                    "action": "blocked",
                    "context_dir": str(context_dir),
                    "resume": blocked_resume(manifest, consistency, maximum),
                    "consistency": consistency,
                }
            return {
                "action": "resumed",
                "context_dir": str(context_dir),
                "resume": resume(context_dir, maximum),
            }
        initialize(root, context_dir, require_task(task))
        return {
            "action": "initialized",
            "context_dir": str(context_dir),
            "resume": resume(context_dir, maximum),
        }

    migrate_ledger(context_dir, root)
    if not context_dir.is_dir():
        raise ValueError("context directory does not exist; start the automatic lifecycle first")

    if event == "switch":
        existing = read_json(context_dir / "manifest.json")
        errors = verify(context_dir, expected_root=root)
        if errors:
            raise ValueError("ledger is invalid: " + "; ".join(errors))
        if existing.get("status") in {"active", "blocked"}:
            checkpoint(
                context_dir,
                require_text(summary, "switch summary"),
                require_text(next_action, "archived task next action"),
                verified.strip(),
                risks.strip(),
                "blocked",
                expected_root=root,
            )
            existing = read_json(context_dir / "manifest.json")
        archived = archive_completed(root, context_dir, existing, reason="explicit_task_switch")
        initialize(root, context_dir, require_task(task))
        return {
            "action": "switched_task",
            "context_dir": str(context_dir),
            "archived_context": str(archived),
            "resume": resume(context_dir, maximum),
        }

    if event == "checkpoint":
        checkpoint(
            context_dir,
            require_text(summary, "summary"),
            require_text(next_action, "next action"),
            verified.strip(),
            risks.strip(),
            status,
            expected_root=root,
        )
        return {"action": "checkpointed", "context_dir": str(context_dir)}

    if event == "change":
        payload = change(
            context_dir,
            require_text(summary, "summary"),
            category=require_text(category, "category"),
            source=require_text(source, "source"),
            impact=impact.strip(),
            requirements=requirements,
            expected_root=root,
        )
        return {"action": "change_recorded", "context_dir": str(context_dir), "change": payload}

    if event == "repair":
        return {"context_dir": str(context_dir), **repair_ledger(root, context_dir)}

    if event == "reconcile":
        return {"action": "reconciled", "context_dir": str(context_dir), **reconcile(context_dir, root)}

    if event == "finish":
        errors = verify(context_dir, expected_root=root)
        if errors:
            raise ValueError("ledger is invalid: " + "; ".join(errors))
        checkpoint(
            context_dir,
            require_text(summary, "summary"),
            require_text(next_action, "next action"),
            verified.strip(),
            risks.strip(),
            "complete",
            expected_root=root,
        )
        return {"action": "finished", "context_dir": str(context_dir)}

    if event == "verify":
        errors = verify(context_dir, expected_root=root)
        return {
            "action": "verified" if not errors else "invalid",
            "context_dir": str(context_dir),
            "errors": errors,
        }

    raise ValueError(f"unsupported automatic event: {event}")


def read_excerpt(path: Path, maximum: int, from_end: bool = False) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= maximum:
        return text
    if from_end:
        return "...\n" + text[-maximum:]
    return text[:maximum] + "\n..."


def blocked_resume(manifest: dict[str, Any], consistency: dict[str, Any], maximum: int) -> str:
    """Render only trusted metadata while the recovery gate is closed."""
    if maximum < 1200:
        raise ValueError("--max-chars must be at least 1200")
    reasons = list(dict.fromkeys(
        [str(item) for item in consistency.get("errors", [])]
        + [str(item) for item in consistency.get("blocking_warnings", [])]
    ))
    payload = {
        "status": "BLOCKED_UNCERTAINTY",
        "task_id": str(manifest.get("task_id", "unknown")),
        "checkpoint": manifest.get("checkpoint", 0),
        "requirements_revision": requirements_revision(manifest),
        "requirements_hash": str(manifest.get("recorded_requirements_hash", "")),
        "baseline_status": consistency.get("baseline_status", "UNKNOWN"),
        "changed_fields": consistency.get("baseline_changed", []),
        "blocking": True,
        "reasons": reasons[:12],
        "next_action": "Inspect the current files, then run the trusted lifecycle checkpoint/rebaseline before editing.",
    }
    rendered = (
        "# Durable Context Resume\n\n"
        f"Task ID: {payload['task_id']} | Status: BLOCKED | Requirements revision: {payload['requirements_revision']}"
        "\n\n## CONTINUITY STATUS\n"
        + json.dumps({
            "baseline_status": payload["baseline_status"],
            "changed_fields": payload["changed_fields"],
            "blocking": True,
        }, ensure_ascii=False, indent=2)
        + "\n\n## RECOVERY GATE\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return rendered[:maximum]


def resume(context_dir: Path, maximum: int) -> str:
    manifest = read_json(context_dir / "manifest.json")
    if maximum < 1200:
        raise ValueError("--max-chars must be at least 1200")
    consistency = reconcile(context_dir)
    if consistency.get("blocking"):
        return blocked_resume(manifest, consistency, maximum)
    continuity = continuity_snapshot(context_dir.parent, context_dir, manifest)
    continuity["budget_used"]["max_chars"] = maximum
    consistency_summary = json.dumps(
        {
            "valid": consistency["valid"],
            "errors": consistency["errors"],
            "warnings": consistency["warnings"],
            "requirements_revision": consistency["requirements_revision"],
        },
        ensure_ascii=False,
        indent=2,
    )
    sections = [
        ("Current Requirements", (context_dir / "requirements.md").read_text(encoding="utf-8"), 0.40),
        ("CONTINUITY STATUS", json.dumps(continuity, ensure_ascii=False, indent=2), 0.18),
        ("Consistency", consistency_summary, 0.12),
        ("Handoff", read_excerpt(context_dir / "handoff.md", maximum), 0.15),
        ("Execution Plan", task_execution_brief(context_dir / "task.md", maximum), 0.08),
        ("Recent Changes", compact_change_entries(consistency["recent_changes"][-5:]), 0.13),
        ("Recent Decisions", read_excerpt(context_dir / "decisions.md", maximum, from_end=True), 0.06),
        ("Recent Findings", read_excerpt(context_dir / "findings.md", maximum, from_end=True), 0.06),
    ]
    navigation = plan_navigation_view(context_dir.parent)
    if navigation.get("configured"):
        sections.insert(
            1,
            (
                "Plan Navigation",
                json.dumps(navigation, ensure_ascii=False, indent=2),
                0.10,
            ),
        )
    return render_budgeted_resume(manifest, maximum, sections)


def verify(
    context_dir: Path,
    ignore_transaction: bool = False,
    expected_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if not ignore_transaction and (context_dir / ".transaction.json").exists():
        errors.append("incomplete ledger transaction exists")
    for name in REQUIRED_FILES:
        path = context_dir / name
        if not path.is_file():
            errors.append(f"missing required file: {name}")

    if errors:
        return errors

    try:
        manifest = read_json(context_dir / "manifest.json")
    except ValueError as exc:
        return [str(exc)]

    for key in (
        "version",
        "task_id",
        "task",
        "status",
        "checkpoint",
        "requirements_revision",
        "last_change_id",
        "last_event_id",
        "recorded_requirements_hash",
        "checkpoint_hashes",
        "continuity_baseline",
        "continuity_index",
        "continuity_status",
        "updated_at",
        "root",
    ):
        if key not in manifest:
            errors.append(f"manifest missing key: {key}")
    if manifest.get("version", 0) < LEDGER_VERSION:
        errors.append(f"ledger requires migration to version {LEDGER_VERSION}")
    task_id = str(manifest.get("task_id", "")).strip()
    if not TASK_ID_PATTERN.fullmatch(task_id):
        errors.append("manifest task_id must be a 32-character lowercase hexadecimal id")
    try:
        manifest_root = canonical_path(manifest.get("root"), "manifest root")
        actual_root = context_dir.resolve().parent
        if manifest_root != actual_root:
            errors.append("manifest root does not match the ledger's actual project root")
        if expected_root is not None and manifest_root != expected_root.resolve():
            errors.append("ledger belongs to a different project root")
    except ValueError as exc:
        errors.append(str(exc))
    if manifest.get("status") not in {"active", "blocked", "complete"}:
        errors.append("manifest status must be active, blocked, or complete")
    if not isinstance(manifest.get("checkpoint"), int) or manifest.get("checkpoint", -1) < 0:
        errors.append("manifest checkpoint must be a non-negative integer")
    if not isinstance(manifest.get("continuity_baseline"), dict):
        errors.append("manifest continuity_baseline must be an object")
    if not isinstance(manifest.get("continuity_index"), dict):
        errors.append("manifest continuity_index must be an object")
    if manifest.get("continuity_status") not in {"UNKNOWN", "UNCHANGED", "CHANGED"}:
        errors.append("manifest continuity_status must be UNKNOWN, UNCHANGED, or CHANGED")

    expected_titles = {
        "task.md": "# Task Execution",
        "requirements.md": "# Current Requirements",
        "findings.md": "# Findings",
        "decisions.md": "# Decisions",
        "handoff.md": "# Resume Brief",
    }
    for name, title in expected_titles.items():
        if not (context_dir / name).read_text(encoding="utf-8").startswith(title):
            errors.append(f"{name} must start with {title!r}")
    task_text = (context_dir / "task.md").read_text(encoding="utf-8")
    _, task_sections = markdown_sections(task_text)
    allowed_task_sections = {"Requirements Reference", "Execution Plan", "Execution Notes"}
    unexpected_task_sections = sorted({name for name, _ in task_sections} - allowed_task_sections)
    if unexpected_task_sections:
        errors.append("task.md contains non-execution sections: " + ", ".join(unexpected_task_sections))
    requirements_text = (context_dir / "requirements.md").read_text(encoding="utf-8")
    objective = requirements_objective(requirements_text)
    if not objective:
        errors.append("requirements.md must contain a non-empty Objective section")
    elif objective != manifest.get("task"):
        errors.append("manifest task does not match requirements Objective")
    document_revision = requirements_document_revision(requirements_text)
    if document_revision != manifest.get("requirements_revision"):
        errors.append("requirements.md revision does not match manifest")
    if file_hash(context_dir / "requirements.md") != manifest.get("recorded_requirements_hash"):
        errors.append("requirements.md contains an unrecorded change")

    handoff_text = (context_dir / "handoff.md").read_text(encoding="utf-8")
    handoff_requirements_hash = re.search(r"(?m)^- Requirements hash: (.+)$", handoff_text)
    handoff_task_id = re.search(r"(?m)^- Task ID: (.+)$", handoff_text)
    handoff_root = re.search(r"(?m)^- Task root: (.+)$", handoff_text)
    handoff_revision = re.search(r"(?m)^- Requirements revision: (\d+)$", handoff_text)
    handoff_checkpoint = re.search(r"(?m)^- Checkpoint: (\d+)$", handoff_text)
    if not handoff_requirements_hash or handoff_requirements_hash.group(1).strip() != str(manifest.get("recorded_requirements_hash", "")):
        errors.append("handoff requirements hash does not match manifest")
    if not handoff_task_id or handoff_task_id.group(1).strip() != task_id:
        errors.append("handoff task_id does not match manifest")
    try:
        handoff_root_matches = bool(handoff_root) and canonical_path(handoff_root.group(1), "handoff root") == canonical_path(manifest.get("root"), "manifest root")
    except ValueError:
        handoff_root_matches = False
    if not handoff_root_matches:
        errors.append("handoff root does not match manifest")
    if not handoff_revision or int(handoff_revision.group(1)) != int(manifest.get("requirements_revision", -1)):
        errors.append("handoff requirements revision does not match manifest")
    if not handoff_checkpoint or int(handoff_checkpoint.group(1)) != int(manifest.get("checkpoint", -1)):
        errors.append("handoff checkpoint does not match manifest")

    checkpoint_count = 0
    for number, line in enumerate((context_dir / "history.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"history.jsonl has invalid JSON on line {number}")
            continue
        if isinstance(entry, dict) and entry.get("kind") == "checkpoint":
            checkpoint_count += 1
    if checkpoint_count != manifest.get("checkpoint"):
        errors.append("manifest checkpoint does not match history checkpoint count")

    change_revision = 0
    previous_event_hash = ""
    last_event_id = ""
    last_change_id = ""
    last_requirement_hash = ""
    seen_ids: set[str] = set()
    for number, line in enumerate((context_dir / "changes.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"changes.jsonl has invalid JSON on line {number}")
            continue
        if not isinstance(entry, dict):
            errors.append(f"changes.jsonl entry on line {number} must be an object")
            continue
        event_id = entry.get("id")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"changes.jsonl entry on line {number} is missing an id")
        elif event_id in seen_ids:
            errors.append(f"changes.jsonl has duplicate id on line {number}")
        else:
            seen_ids.add(event_id)
            last_event_id = event_id
        if entry.get("previous_event_hash", "") != previous_event_hash:
            errors.append(f"changes.jsonl hash chain is broken on line {number}")
        expected_event_hash = change_event_hash(entry)
        if entry.get("event_hash") != expected_event_hash:
            errors.append(f"changes.jsonl event hash is invalid on line {number}")
        previous_event_hash = str(entry.get("event_hash", ""))
        if entry.get("kind") == "task_started":
            if entry.get("revision") != 0:
                errors.append(f"task_started revision must be 0 on line {number}")
            last_change_id = str(event_id or "")
            after = entry.get("requirements_after")
            if not isinstance(after, str):
                errors.append(f"task_started requirements snapshot is missing on line {number}")
            elif entry.get("requirements_hash") != sha256_text(after):
                errors.append(f"task_started requirements hash is invalid on line {number}")
            elif isinstance(after, str):
                last_requirement_hash = str(entry.get("requirements_hash"))
        if entry.get("kind") == "requirement_change":
            before = entry.get("before_revision")
            revision = entry.get("after_revision")
            if before != change_revision or not isinstance(revision, int) or revision != change_revision + 1:
                errors.append(f"changes.jsonl has a broken requirement revision chain on line {number}")
            else:
                change_revision = revision
            last_change_id = str(event_id or "")
            after = entry.get("requirements_after")
            if not isinstance(after, str):
                errors.append(f"requirement snapshot is missing on line {number}")
            elif isinstance(after, str) and entry.get("requirements_hash") != sha256_text(after):
                errors.append(f"requirement snapshot hash is invalid on line {number}")
            elif isinstance(after, str):
                last_requirement_hash = str(entry.get("requirements_hash"))
    if change_revision != manifest.get("requirements_revision"):
        errors.append("manifest requirements revision does not match changes.jsonl")
    if last_event_id != manifest.get("last_event_id"):
        errors.append("manifest last_event_id does not match changes.jsonl")
    if last_change_id != manifest.get("last_change_id"):
        errors.append("manifest last_change_id does not match changes.jsonl")
    if last_requirement_hash and last_requirement_hash != manifest.get("recorded_requirements_hash"):
        errors.append("latest requirement event hash does not match current requirements")
    if manifest.get("status") == "complete":
        verification_match = re.search(
            r"(?ms)^## Verification\s*\n(.*?)(?:\n## |\Z)",
            handoff_text,
        )
        if not verification_match or not verification_match.group(1).strip() or verification_match.group(1).strip().startswith("Not provided"):
            errors.append("complete ledger must contain verification evidence in handoff")
        acceptance = requirements_section(requirements_text, "Acceptance Standard")
        if re.search(r"(?m)^\s*- \[ \]", acceptance):
            errors.append("complete ledger has unfinished Acceptance Standard items")
    return errors


def status(context_dir: Path) -> dict[str, Any]:
    manifest = read_json(context_dir / "manifest.json")
    return {
        "context_dir": str(context_dir),
        "manifest": manifest,
        "files": {name: (context_dir / name).stat().st_size for name in REQUIRED_FILES if (context_dir / name).exists()},
        "verification_errors": verify(context_dir),
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="durable-context-") as temporary:
        root = Path(temporary)
        context_dir = root / DEFAULT_DIR
        started = automatic(
            root,
            context_dir,
            "start",
            "Verify durable context state handling",
            "",
            "",
            "",
            "",
            "active",
            3000,
        )
        automatic(
            root,
            context_dir,
            "checkpoint",
            "",
            "Created and checked the ledger.",
            "Run verification.",
            "self-test",
            "",
            "active",
            3000,
        )
        changed = automatic(
            root,
            context_dir,
            "change",
            task="",
            summary="Review standard changed.",
            next_action="Tests must use the revised standard.",
            verified="",
            risks="",
            status="active",
            maximum=3000,
            category="acceptance",
            source="self-test",
            impact="verification behavior changes",
            requirements="# Current Requirements\n\n## Objective\nVerify durable context state handling\n\n## Acceptance Standard\n- [x] Preserve revision history.\n\n## Current Route\n- [ ] Run verification.\n\n## Revision Log\n",
        )
        pending = reconcile(context_dir)
        automatic(
            root,
            context_dir,
            "checkpoint",
            "",
            "Captured the revised standard.",
            "Run final verification.",
            "self-test",
            "",
            "active",
            3000,
        )
        errors = verify(context_dir)
        output = resume(context_dir, 3000)
        try:
            resume(context_dir, 100)
        except ValueError:
            rejected_small_budget = True
        else:
            rejected_small_budget = False
        if (
            errors
            or not rejected_small_budget
            or not changed["change"].get("after_revision") == 1
            or pending["warnings"]
            or "Captured the revised standard." not in output
            or "CONTINUITY STATUS" not in output
            or not isinstance(read_json(context_dir / "manifest.json").get("continuity_baseline"), dict)
            or "Plan Navigation" in started.get("resume", "")
        ):
            raise RuntimeError(f"self-test failed: {errors}")

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
        navigation = inspect_plan_navigation(root)
        changed_baseline = continuity_snapshot(root, context_dir, read_json(context_dir / "manifest.json"))
        navigation_resume = resume(context_dir, 3000)
        if (
            not navigation.get("valid")
            or navigation.get("current_route_coordinate") != "R7:A3/B2"
            or changed_baseline.get("baseline_status") != "CHANGED"
            or "plans_hash" not in changed_baseline.get("changed_fields", [])
            or "RECOVERY GATE" not in navigation_resume
        ):
            raise RuntimeError("self-test failed: plan drift was not gated")
        checkpoint(
            context_dir,
            "Rebaselined the verified navigation plan.",
            "Continue navigation checks.",
            "self-test",
            "",
            "active",
            expected_root=root,
        )
        navigation_resume = resume(context_dir, 3000)
        if "Plan Navigation" not in navigation_resume or "R7:A3/B2" not in navigation_resume:
            raise RuntimeError("self-test failed: verified plan navigation was not restored")

        invalid_plan = valid_plan.replace("route_id: R7", "route_id: R8")
        (root / "PLANS.md").write_text(invalid_plan, encoding="utf-8")
        invalid_navigation = inspect_plan_navigation(root)
        invalid_resume = resume(context_dir, 3000)
        if (
            invalid_navigation.get("valid")
            or not invalid_navigation.get("errors")
            or '\"current_route_coordinate\": \"R7:A3/B2\"' in invalid_resume
        ):
            raise RuntimeError("self-test failed: invalid plan navigation was trusted")

        continuity_plan = """# Active Execution Plan

plan_id: PLAN-01
status: active
authority: exclusive
current_task_id: login-fix
latest_change_class: priority_branch
on_complete: resume:android-session-recovery
route_id: R7
current_route_coordinate: R7:A3/B2/C1
continuity_parent_task_id: android-session-recovery

## Milestones

| Task ID | Status | Route coordinate | Outcome |
| --- | --- | --- | --- |
| android-session-recovery | deferred | R7:A3/B2 | Resume the Android session. |
| login-fix | in_progress | R7:A3/B2/C1 | Repair login first. |
"""
        (root / "PLANS.md").write_text(continuity_plan, encoding="utf-8")
        continuity_navigation = inspect_plan_navigation(root)
        if (
            not continuity_navigation.get("valid")
            or continuity_navigation.get("continuity_parent_task_id") != "android-session-recovery"
            or continuity_navigation.get("on_complete") != "resume:android-session-recovery"
        ):
            raise RuntimeError("self-test failed: valid continuity navigation was rejected")

    with tempfile.TemporaryDirectory(prefix="durable-context-adversarial-") as temporary:
        root = Path(temporary)
        context_dir = root / DEFAULT_DIR
        automatic(root, context_dir, "start", "Task A", "", "", "", "", "active", 3000)
        conflict = automatic(root, context_dir, "start", "Task B", "", "", "", "", "active", 3000)
        if conflict.get("action") != "objective_conflict":
            raise RuntimeError("self-test failed: active objective mismatch was not blocked")
        switched = automatic(
            root,
            context_dir,
            "switch",
            "Task B",
            "Task A paused for a distinct task.",
            "Resume Task A only when explicitly requested.",
            "self-test",
            "",
            "active",
            3000,
        )
        if switched.get("action") != "switched_task" or verify(context_dir):
            raise RuntimeError("self-test failed: explicit task switch did not preserve a valid ledger")

        requirements_path = context_dir / "requirements.md"
        recorded_requirements = requirements_path.read_text(encoding="utf-8")
        atomic_write(requirements_path, recorded_requirements + "\nUNRECORDED_CHANGE\n")
        try:
            checkpoint(context_dir, "Must fail", "No action", "", "", "active")
        except ValueError as exc:
            rejected_unrecorded = "unrecorded requirements change" in str(exc)
        else:
            rejected_unrecorded = False
        if not rejected_unrecorded or (context_dir / ".transaction.json").exists():
            raise RuntimeError("self-test failed: unrecorded requirements change was accepted")
        atomic_write(requirements_path, recorded_requirements)

        long_snapshot = (
            "# Current Requirements\n\n## Objective\nTask B\n\n## Acceptance Standard\n"
            + ("x" * 5000)
            + "\n\n## Current Route\nLATEST_ROUTE_MARKER\n"
        )
        change(context_dir, "Route changed", "route", "self-test", "route", long_snapshot)
        bounded_resume = resume(context_dir, 1200)
        if len(bounded_resume) > 1200 or "LATEST_ROUTE_MARKER" not in bounded_resume:
            raise RuntimeError("self-test failed: structured requirements resume lost the current route")
        change(context_dir, "Set icon spacing to exactly 8px", "detail", "self-test", "UI detail", "")
        for number in range(9):
            checkpoint(context_dir, f"Detail retention checkpoint {number}", "Continue", "self-test", "", "active")
        if "8px" not in (context_dir / "requirements.md").read_text(encoding="utf-8") or "8px" not in resume(
            context_dir, 3000
        ):
            raise RuntimeError("self-test failed: detail revision disappeared from current context")
        manifest_backup = (context_dir / "manifest.json").read_text(encoding="utf-8")
        atomic_write(
            context_dir / ".transaction.json",
            json.dumps(
                {
                    "id": "self-test-transaction",
                    "kind": "checkpoint",
                    "started_at": utc_now(),
                    "backups": {"manifest.json": manifest_backup},
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
        )
        atomic_write(context_dir / "manifest.json", "{}\n")
        recovered = automatic(root, context_dir, "recover", "", "", "", "", "", "active", 3000)
        if recovered.get("action") != "transaction_recovered" or verify(context_dir):
            raise RuntimeError("self-test failed: incomplete transaction was not recovered")
        manifest = read_json(context_dir / "manifest.json")
        manifest["last_change_id"] = "forged-id"
        write_manifest(context_dir, manifest)
        if not any("last_change_id" in error for error in verify(context_dir)):
            raise RuntimeError("self-test failed: forged change pointer was not detected")

        try:
            normalize_requirements(
                "# Current Requirements\n\n## Objective\nA\n\n## Objective\nB\n",
                0,
            )
        except ValueError:
            duplicate_section_rejected = True
        else:
            duplicate_section_rejected = False
        if not duplicate_section_rejected:
            raise RuntimeError("self-test failed: duplicate requirements sections were accepted")
        try:
            change(context_dir, "bad\n## injected", "detail", "self-test", "", "")
        except ValueError:
            heading_injection_rejected = True
        else:
            heading_injection_rejected = False
        if not heading_injection_rejected:
            raise RuntimeError("self-test failed: detail heading injection was accepted")
        if not any("different project root" in error for error in verify(context_dir, expected_root=root / "other")):
            raise RuntimeError("self-test failed: cross-project ledger validation was not enforced")

    with tempfile.TemporaryDirectory(prefix="durable-context-complete-") as temporary:
        root = Path(temporary)
        context_dir = root / DEFAULT_DIR
        automatic(root, context_dir, "start", "Completion validation", "", "", "", "", "active", 3000)
        accepted = (context_dir / "requirements.md").read_text(encoding="utf-8").replace(
            "- [ ] Define the completion evidence.", "- [x] Define the completion evidence."
        )
        change(context_dir, "Acceptance evidence recorded", "acceptance", "self-test", "", accepted)
        try:
            checkpoint(context_dir, "Must reject empty evidence", "No action", "", "", "complete")
        except ValueError as exc:
            if "verification evidence" not in str(exc):
                raise
        else:
            raise RuntimeError("self-test failed: complete checkpoint accepted empty evidence")
        checkpoint(context_dir, "Completion validated", "No further action", "self-test passed", "", "complete")
        if verify(context_dir):
            raise RuntimeError("self-test failed: valid complete ledger did not verify")
    print("self-test passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"relative context directory (default: {DEFAULT_DIR})")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_location_arguments(command_parser: argparse.ArgumentParser) -> None:
        # Accept location flags before or after the subcommand without overriding parent values.
        command_parser.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        command_parser.add_argument("--dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    init_parser = subparsers.add_parser("init", help="create a new ledger")
    add_location_arguments(init_parser)
    init_parser.add_argument("--task", required=True, help="task objective")

    checkpoint_parser = subparsers.add_parser("checkpoint", help="record a resumable checkpoint")
    add_location_arguments(checkpoint_parser)
    checkpoint_parser.add_argument("--summary", required=True, help="verified progress summary")
    checkpoint_parser.add_argument("--next-action", required=True, help="single next action")
    checkpoint_parser.add_argument("--verified", default="", help="test or evidence")
    checkpoint_parser.add_argument("--risks", default="", help="remaining risks or blockers")
    checkpoint_parser.add_argument("--status", choices=("active", "blocked", "complete"), default="active")

    status_parser = subparsers.add_parser("status", help="print machine-readable status")
    add_location_arguments(status_parser)
    resume_parser = subparsers.add_parser("resume", help="print a compact resume brief")
    add_location_arguments(resume_parser)
    resume_parser.add_argument("--max-chars", type=int, default=3600, help="maximum resume output size")
    verify_parser = subparsers.add_parser("verify", help="validate ledger structure")
    add_location_arguments(verify_parser)
    auto_parser = subparsers.add_parser("auto", help=argparse.SUPPRESS)
    add_location_arguments(auto_parser)
    auto_parser.add_argument("--event", choices=("start", "recover", "switch", "checkpoint", "change", "repair", "reconcile", "finish", "verify"), required=True, help=argparse.SUPPRESS)
    auto_parser.add_argument("--task", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--summary", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--next-action", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--verified", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--risks", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--status", choices=("active", "blocked", "complete"), default="active", help=argparse.SUPPRESS)
    auto_parser.add_argument("--max-chars", type=int, default=3600, help=argparse.SUPPRESS)
    auto_parser.add_argument("--category", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--source", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--impact", default="", help=argparse.SUPPRESS)
    auto_parser.add_argument("--requirements", default="", help=argparse.SUPPRESS)
    subparsers.add_parser("self-test", help="run an isolated script self-test")
    return parser


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (AttributeError, TypeError, ValueError):
            continue
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
            return 0

        root, context_dir = resolve_context_dir(args.root, args.dir)
        if args.command == "init":
            initialize(root, context_dir, require_task(args.task))
            print(json.dumps({"context_dir": str(context_dir), "status": "initialized"}, ensure_ascii=False))
            return 0

        if args.command == "auto":
            payload = automatic(
                root,
                context_dir,
                args.event,
                args.task,
                args.summary,
                args.next_action,
                args.verified,
                args.risks,
                args.status,
                args.max_chars,
                args.category,
                args.source,
                args.impact,
                args.requirements,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if context_dir.is_dir():
            migrate_ledger(context_dir, root)

        if not context_dir.is_dir():
            raise ValueError(f"context directory does not exist: {context_dir}")

        if args.command == "checkpoint":
            checkpoint(
                context_dir,
                require_text(args.summary, "summary"),
                require_text(args.next_action, "next action"),
                args.verified.strip(),
                args.risks.strip(),
                args.status,
                expected_root=root,
            )
            print(json.dumps({"context_dir": str(context_dir), "status": "checkpointed"}, ensure_ascii=False))
            return 0
        if args.command == "status":
            print(json.dumps(status(context_dir), ensure_ascii=False, indent=2))
            return 0
        if args.command == "resume":
            print(resume(context_dir, args.max_chars))
            return 0
        if args.command == "verify":
            errors = verify(context_dir, expected_root=root)
            if errors:
                print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
                return 1
            print("ledger is valid")
            return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
