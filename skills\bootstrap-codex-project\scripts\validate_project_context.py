#!/usr/bin/env python3
"""Validate a project's generated context files without modifying the project."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


EXCLUDED_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
MAX_MARKDOWN_FILES = 2000
MAX_MARKDOWN_TOTAL_BYTES = 8 * 1024 * 1024
MAX_MARKDOWN_FILE_BYTES = 512 * 1024

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9][A-Z0-9_ -]*\}\}")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
}
PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)"
)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
FENCED_CODE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
PACKAGE_MANAGERS = {"npm", "pnpm", "yarn", "bun"}
LOCKFILE_MANAGERS = {
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
}
PACKAGE_BUILTINS = {
    "npm": {
        "adduser", "audit", "ci", "config", "dedupe", "exec", "help", "init",
        "install", "link", "login", "logout", "pack", "ping", "publish", "rebuild",
        "remove", "uninstall", "update", "version", "view", "whoami",
    },
    "pnpm": {
        "add", "audit", "config", "create", "deploy", "dlx", "exec", "fetch", "import",
        "init", "install", "link", "list", "outdated", "pack", "patch", "prune", "publish",
        "rebuild", "remove", "store", "unlink", "update", "why",
    },
    "yarn": {
        "add", "cache", "config", "create", "dlx", "exec", "help", "info", "init",
        "install", "link", "npm", "pack", "plugin", "remove", "set", "unlink", "up",
        "version", "why", "workspace", "workspaces",
    },
    "bun": {
        "add", "build", "create", "dev", "help", "init", "install", "link", "pm", "publish",
        "remove", "repl", "test", "unlink", "update", "upgrade", "x",
    },
}
OPTIONS_WITH_VALUE = {"--dir", "--filter", "--workspace", "-C", "-F"}
VAGUE_AGENT_PATTERNS = {
    "best practices": re.compile(r"\bbest practices?\b", re.IGNORECASE),
    "generic quality": re.compile(r"\b(?:high[- ]quality code|clean code)\b", re.IGNORECASE),
    "impossible perfection": re.compile(r"\bnever make mistakes?\b", re.IGNORECASE),
    "Chinese best practices": re.compile(r"(?:遵循|按照)最佳实践"),
    "Chinese generic quality": re.compile(r"(?:编写|保持|确保)高质量代码"),
    "Chinese impossible perfection": re.compile(r"(?:不要|不能|永远不要)犯错"),
}
PLAN_FIELD_RE = re.compile(
    r"^\s*(plan_id|status|authority|current_task_id|continuation_policy|completion_policy|priority_basis|delivery_contract|latest_change_id|latest_change_class|change_authority_reference|delegated_execution|on_complete|route_id|current_route_coordinate|continuity_parent_task_id|execution_authority|record_kind|active_plan)\s*:\s*(.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ROADMAP_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[\s*\]", re.MULTILINE)
ALLOWED_PLAN_STATUSES = {"active", "paused", "completed", "superseded", "archived"}
ALLOWED_AUTHORITIES = {"exclusive", "none"}
ALLOWED_CHANGE_CLASSES = {"task_adjustment", "priority_branch", "roadmap_change"}
ON_COMPLETE_RE = re.compile(
    r"^(?:wait|resume:[A-Za-z0-9._-]+|activate:[A-Za-z0-9._-]+)$"
)
ALLOWED_CONTINUATION_POLICIES = {"validate_then_advance"}
ALLOWED_COMPLETION_POLICIES = {"all_required_items"}
MILESTONE_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*(pending|in_progress|completed|blocked|deferred)\s*\|",
    re.IGNORECASE | re.MULTILINE,
)
ROUTE_ID_RE = re.compile(r"^R[1-9][0-9]*$")
ROUTE_COORDINATE_RE = re.compile(
    r"^(?P<route>R[1-9][0-9]*):A(?P<a>[1-9][0-9]*)"
    r"(?:/B(?P<b>[1-9][0-9]*))?(?:/C(?P<c>[1-9][0-9]*))?$"
)
MANUAL_COMMAND_PREFIXES = {
    "cargo", "dotnet", "go", "gradle", "gradlew", "make", "mvn", "mvnw",
    "py", "pytest", "python", "python3",
}

PROFILE_REQUIRED = {
    "minimal": ["README.md", "AGENTS.md"],
    "standard": [
        "README.md",
        "AGENTS.md",
        "docs/INDEX.md",
        "docs/product.md",
        "docs/architecture.md",
    ],
    "advanced": [
        "README.md",
        "AGENTS.md",
        "docs/INDEX.md",
        "docs/product.md",
        "docs/architecture.md",
    ],
}


def planning_artifact_kind(path: str) -> str | None:
    """Classify exact and versioned planning filenames without substring traps."""
    stem = Path(path).stem.lower()
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", stem)
        if token
    }
    if "roadmap" in tokens:
        return "roadmap"
    if "handoff" in tokens:
        return "handoff"
    if tokens & {"plan", "planning", "plans"}:
        return "plan"
    if tokens & {"task", "tasks", "todo", "todos"}:
        return "tasks"
    if "current" in tokens:
        return "current"
    return None


def markdown_files(root: Path) -> list[Path]:
    results: list[Path] = []
    total_bytes = 0
    truncated = False
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(names):
            if not name.lower().endswith(".md"):
                continue
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if (
                rel in {"README.md", "PLANS.md"}
                or rel.startswith("docs/")
                or name in {"AGENTS.md", "AGENTS.override.md"}
                or planning_artifact_kind(name) is not None
            ):
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                if (
                    len(results) >= MAX_MARKDOWN_FILES
                    or total_bytes + min(size, MAX_MARKDOWN_FILE_BYTES) > MAX_MARKDOWN_TOTAL_BYTES
                ):
                    truncated = True
                    continue
                results.append(path)
                total_bytes += min(size, MAX_MARKDOWN_FILE_BYTES)
    markdown_files.last_scan = {
        "file_count": len(results),
        "total_bytes": total_bytes,
        "truncated": truncated,
    }
    return sorted(results)


def local_link_target(source: Path, root: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    link_path = unquote(parsed.path)
    if not link_path:
        return None
    if link_path.startswith("/"):
        return (root / link_path.lstrip("/")).resolve()
    return (source.parent / link_path).resolve()


def read_package_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def repository_package_facts(root: Path) -> tuple[set[str], set[str]]:
    managers: set[str] = set()
    scripts: set[str] = set()

    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in names:
            if name in LOCKFILE_MANAGERS:
                managers.add(LOCKFILE_MANAGERS[name])
            if name != "package.json":
                continue
            data = read_package_json(Path(current) / name)
            if data is None:
                continue
            declared_manager = data.get("packageManager")
            if isinstance(declared_manager, str):
                manager = declared_manager.split("@", 1)[0].lower()
                if manager in PACKAGE_MANAGERS:
                    managers.add(manager)
            declared_scripts = data.get("scripts")
            if isinstance(declared_scripts, dict):
                scripts.update(str(key) for key in declared_scripts)

    return managers, scripts


def command_snippets(text: str) -> list[str]:
    snippets = [match.strip() for match in INLINE_CODE_RE.findall(text)]
    for block in FENCED_CODE_RE.findall(text):
        snippets.extend(line.strip() for line in block.splitlines() if line.strip())
    return snippets


def parse_package_command(snippet: str) -> tuple[str, str | None] | None:
    try:
        tokens = shlex.split(snippet, posix=True)
    except ValueError:
        return None
    if tokens and tokens[0] in {"$", ">"}:
        tokens = tokens[1:]
    if not tokens or tokens[0].lower() not in PACKAGE_MANAGERS:
        return None

    manager = tokens[0].lower()
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index].split("=", 1)[0]
        index += 1
        if option in OPTIONS_WITH_VALUE and "=" not in tokens[index - 1] and index < len(tokens):
            index += 1
    if index >= len(tokens):
        return manager, None
    if tokens[index] in {"run", "run-script"}:
        index += 1
    if index >= len(tokens):
        return manager, None

    command = tokens[index]
    if command in PACKAGE_BUILTINS[manager]:
        return manager, None
    return manager, command


def substantive_lines(text: str) -> set[str]:
    lines: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "```", "|")):
            continue
        line = re.sub(r"^(?:[-*+] |\d+[.)] )", "", line)
        normalized = re.sub(r"\s+", " ", line).strip().lower()
        if len(normalized) >= 20:
            lines.add(normalized)
    return lines


def planning_fields(text: str) -> dict[str, str]:
    return {
        key.lower(): value.strip()
        for key, value in PLAN_FIELD_RE.findall(text)
    }


def planning_field_duplicates(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in PLAN_FIELD_RE.findall(text):
        values.setdefault(key.lower(), []).append(value.strip())
    return {key: entries for key, entries in values.items() if len(entries) > 1}


def manual_command_claim(snippet: str) -> str | None:
    try:
        tokens = shlex.split(snippet, posix=True)
    except ValueError:
        return None
    if tokens and tokens[0] in {"$", ">"}:
        tokens = tokens[1:]
    if not tokens:
        return None
    command = Path(tokens[0]).name.lower()
    command = command.removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")
    return command if command in MANUAL_COMMAND_PREFIXES else None


def has_heading(text: str, heading: str) -> bool:
    return bool(
        re.search(
            rf"^##\s+{re.escape(heading)}\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def markdown_section_body(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def split_markdown_row(line: str) -> list[str]:
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return []
    return [cell.strip() for cell in value[1:-1].split("|")]


def milestone_table(text: str) -> tuple[list[dict[str, str]], bool]:
    body = markdown_section_body(text, "Milestones")
    lines = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], False
    headers = [re.sub(r"\s+", " ", item.strip().lower()) for item in split_markdown_row(lines[0])]
    if "task id" not in headers or "status" not in headers:
        return [], False
    coordinate_header = next(
        (name for name in ("route coordinate", "coordinate") if name in headers),
        None,
    )
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = split_markdown_row(line)
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


def validate_plan_navigation(
    rel: str,
    text: str,
    fields: dict[str, str],
    errors: list[dict[str, str]],
) -> dict[str, object] | None:
    navigation_fields = (
        "route_id",
        "current_route_coordinate",
        "continuity_parent_task_id",
    )
    enabled = any(fields.get(field, "").strip() for field in navigation_fields)
    rows, has_coordinate_column = milestone_table(text)
    if has_coordinate_column and any(
        row["coordinate"].strip().lower() not in {"", "none", "-"}
        for row in rows
    ):
        enabled = True
    if not enabled:
        return None

    navigation_errors: list[tuple[str, str]] = []
    route_id = fields.get("route_id", "").strip()
    current_coordinate = fields.get("current_route_coordinate", "").strip()
    continuity_parent = fields.get("continuity_parent_task_id", "").strip()
    current_task = fields.get("current_task_id", "").strip()
    on_complete = fields.get("on_complete", "").strip()
    change_class = fields.get("latest_change_class", "").strip().lower()

    if not route_id:
        navigation_errors.append(("incomplete-plan-navigation", "route_id"))
    elif not ROUTE_ID_RE.fullmatch(route_id):
        navigation_errors.append(("invalid-route-id", route_id))

    coordinate_match = ROUTE_COORDINATE_RE.fullmatch(current_coordinate)
    if not current_coordinate:
        navigation_errors.append(("incomplete-plan-navigation", "current_route_coordinate"))
    elif not coordinate_match:
        navigation_errors.append(("invalid-route-coordinate", current_coordinate))
    elif route_id and coordinate_match.group("route") != route_id:
        navigation_errors.append(
            (
                "route-coordinate-mismatch",
                f"route_id={route_id}, coordinate={current_coordinate}",
            )
        )

    row_by_task = {row["task_id"]: row for row in rows}
    coordinate_by_task: dict[str, str] = {}
    seen_coordinates: dict[str, str] = {}
    if has_coordinate_column:
        for row in rows:
            coordinate = row["coordinate"].strip()
            if coordinate.lower() in {"", "none", "-"}:
                continue
            match = ROUTE_COORDINATE_RE.fullmatch(coordinate)
            if not match:
                navigation_errors.append(
                    ("invalid-milestone-route-coordinate", f"{row['task_id']}: {coordinate}")
                )
                continue
            if route_id and match.group("route") != route_id:
                navigation_errors.append(
                    ("milestone-route-mismatch", f"{row['task_id']}: {coordinate}")
                )
            if coordinate in seen_coordinates:
                navigation_errors.append(
                    (
                        "duplicate-route-coordinate",
                        f"{coordinate}: {seen_coordinates[coordinate]}, {row['task_id']}",
                    )
                )
            else:
                seen_coordinates[coordinate] = row["task_id"]
            coordinate_by_task[row["task_id"]] = coordinate
        if current_task and current_task not in coordinate_by_task:
            navigation_errors.append(
                ("current-task-missing-route-coordinate", current_task)
            )
        elif current_task and current_coordinate and coordinate_by_task.get(current_task) != current_coordinate:
            navigation_errors.append(
                (
                    "current-task-route-mismatch",
                    f"{current_task}: {coordinate_by_task.get(current_task)} != {current_coordinate}",
                )
            )

    is_continuity_work = bool(coordinate_match and coordinate_match.group("c"))
    if is_continuity_work:
        if not continuity_parent or continuity_parent.lower() in {"none", "-"}:
            navigation_errors.append(
                ("continuity-parent-required", current_coordinate)
            )
        else:
            parent_row = row_by_task.get(continuity_parent)
            if parent_row is None:
                navigation_errors.append(
                    ("continuity-parent-not-in-milestones", continuity_parent)
                )
            elif parent_row["status"] not in {"deferred", "blocked"}:
                navigation_errors.append(
                    (
                        "continuity-parent-not-paused",
                        f"{continuity_parent}: {parent_row['status']}",
                    )
                )
            expected_resume = f"resume:{continuity_parent}"
            if on_complete != expected_resume:
                navigation_errors.append(
                    (
                        "continuity-return-mismatch",
                        f"expected {expected_resume}, found {on_complete or 'missing'}",
                    )
                )
        if change_class != "priority_branch":
            navigation_errors.append(
                ("continuity-work-not-priority-branch", change_class or "missing")
            )
    elif continuity_parent and continuity_parent.lower() not in {"none", "-"}:
        navigation_errors.append(
            ("unexpected-continuity-parent", continuity_parent)
        )

    for code, detail in navigation_errors:
        errors.append({"code": code, "path": rel, "detail": detail})

    if navigation_errors or coordinate_match is None:
        return None
    return {
        "path": rel,
        "plan_id": fields.get("plan_id", ""),
        "route_id": route_id,
        "current_task_id": current_task,
        "current_route_coordinate": current_coordinate,
        "continuity_parent_task_id": (
            continuity_parent
            if continuity_parent and continuity_parent.lower() not in {"none", "-"}
            else None
        ),
        "source": "active exclusive PLANS.md",
    }


def validate_planning_authority(
    root: Path,
    files: list[Path],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    info: list[dict[str, object]],
) -> None:
    planning_records: list[tuple[Path, str, dict[str, str]]] = []
    active_plans: list[str] = []
    roadmap_paths: list[str] = []
    checkpoint_paths: list[str] = []
    noncanonical_planning_paths: list[str] = []
    undeclared_roadmap_authority: list[str] = []
    undeclared_checkpoint_authority: list[str] = []
    plan_navigation: list[dict[str, object]] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        fields = planning_fields(text)
        for field, values in planning_field_duplicates(text).items():
            normalized = {value.strip().lower() for value in values}
            target = errors if len(normalized) > 1 else warnings
            target.append(
                {
                    "code": (
                        "conflicting-plan-field"
                        if len(normalized) > 1
                        else "duplicate-plan-field"
                    ),
                    "path": rel,
                    "detail": f"{field}: {', '.join(values)}",
                }
            )
        name = path.name.lower()
        kind = planning_artifact_kind(name)
        is_plan = name in {"plan.md", "plans.md"} or "plan_id" in fields
        is_canonical_roadmap = rel == "docs/roadmap.md"
        is_roadmap = is_canonical_roadmap or kind == "roadmap"
        is_checkpoint = rel == "docs/work/current.md" or fields.get("record_kind", "").lower() == "checkpoint"
        is_noncanonical_planning = (
            kind is not None
            and not is_plan
            and not is_checkpoint
            and not is_canonical_roadmap
        )

        if not (is_plan or is_roadmap or is_checkpoint or is_noncanonical_planning):
            continue
        planning_records.append((path, text, fields))

        if is_noncanonical_planning:
            noncanonical_planning_paths.append(rel)
            warnings.append(
                {
                    "code": "noncanonical-planning-artifact",
                    "path": rel,
                    "detail": (
                        f"detected {kind}; classify it as reference, archive, "
                        "roadmap, checkpoint, or active plan before selecting work"
                    ),
                }
            )

        if is_roadmap:
            roadmap_paths.append(rel)
            authority = fields.get("execution_authority", "").lower()
            if not authority:
                if is_canonical_roadmap:
                    undeclared_roadmap_authority.append(rel)
            elif authority != "none":
                errors.append(
                    {
                        "code": "roadmap-has-execution-authority",
                        "path": rel,
                        "detail": f"execution_authority must be none, found {authority}",
                    }
                )
            if ROADMAP_CHECKBOX_RE.search(text):
                warnings.append(
                    {
                        "code": "actionable-roadmap-checklist",
                        "path": rel,
                        "detail": "unchecked tasks can be mistaken for currently authorized work",
                    }
                )

        if is_checkpoint:
            checkpoint_paths.append(rel)
            if fields.get("record_kind", "").lower() != "checkpoint":
                warnings.append(
                    {
                        "code": "checkpoint-kind-undeclared",
                        "path": rel,
                        "detail": "declare record_kind: checkpoint",
                    }
                )
            checkpoint_authority = fields.get("execution_authority", "").lower()
            if not checkpoint_authority:
                undeclared_checkpoint_authority.append(rel)
            elif checkpoint_authority != "none":
                errors.append(
                    {
                        "code": "checkpoint-has-execution-authority",
                        "path": rel,
                        "detail": f"execution_authority must be none, found {checkpoint_authority}",
                    }
                )

        if not is_plan:
            continue

        status = fields.get("status", "").lower()
        authority = fields.get("authority", "").lower()
        if status and status not in ALLOWED_PLAN_STATUSES:
            errors.append(
                {
                    "code": "invalid-plan-status",
                    "path": rel,
                    "detail": status,
                }
            )
        if authority and authority not in ALLOWED_AUTHORITIES:
            errors.append(
                {
                    "code": "invalid-plan-authority",
                    "path": rel,
                    "detail": authority,
                }
            )
        if authority == "exclusive" and status != "active":
            errors.append(
                {
                    "code": "exclusive-plan-not-active",
                    "path": rel,
                    "detail": f"status is {status or 'missing'}",
                }
            )

        if status != "active":
            continue

        active_plans.append(rel)
        if rel != "PLANS.md":
            errors.append(
                {
                    "code": "active-plan-not-canonical",
                    "path": rel,
                    "detail": "the active execution plan must be root PLANS.md",
                }
            )
        required = (
            "plan_id",
            "authority",
            "current_task_id",
            "latest_change_id",
            "latest_change_class",
            "change_authority_reference",
            "on_complete",
        )
        missing = [field for field in required if not fields.get(field)]
        if missing:
            errors.append(
                {
                    "code": "incomplete-active-plan",
                    "path": rel,
                    "detail": ", ".join(missing),
                }
            )
        execution_fields = (
            "continuation_policy",
            "completion_policy",
            "priority_basis",
            "delivery_contract",
        )
        missing_execution = [
            field for field in execution_fields if not fields.get(field)
        ]
        if missing_execution:
            errors.append(
                {
                    "code": "incomplete-execution-discipline",
                    "path": rel,
                    "detail": ", ".join(missing_execution),
                }
            )
        continuation_policy = fields.get("continuation_policy", "").lower()
        if (
            continuation_policy
            and continuation_policy not in ALLOWED_CONTINUATION_POLICIES
        ):
            errors.append(
                {
                    "code": "invalid-continuation-policy",
                    "path": rel,
                    "detail": continuation_policy,
                }
            )
        completion_policy = fields.get("completion_policy", "").lower()
        if completion_policy and completion_policy not in ALLOWED_COMPLETION_POLICIES:
            errors.append(
                {
                    "code": "invalid-completion-policy",
                    "path": rel,
                    "detail": completion_policy,
                }
            )
        if authority and authority != "exclusive":
            errors.append(
                {
                    "code": "active-plan-not-exclusive",
                    "path": rel,
                    "detail": authority,
                }
            )

        change_class = fields.get("latest_change_class", "").lower()
        if change_class and change_class not in ALLOWED_CHANGE_CLASSES:
            errors.append(
                {
                    "code": "invalid-requirement-change-class",
                    "path": rel,
                    "detail": change_class,
                }
            )
        authority_reference = fields.get("change_authority_reference", "").lower()
        if change_class == "roadmap_change" and authority_reference in {"", "none"}:
            errors.append(
                {
                    "code": "roadmap-change-without-authority-reference",
                    "path": rel,
                    "detail": "reference the durable product, architecture, compatibility, safety, or decision document",
                }
            )
        if change_class == "priority_branch":
            if not has_heading(text, "Deferred work"):
                errors.append(
                    {
                        "code": "priority-branch-without-deferred-work",
                        "path": rel,
                        "detail": "record the paused work and its resume condition",
                    }
                )
            lowered = text.lower()
            for label in ("reason deferred", "impact", "resume condition"):
                if label not in lowered:
                    errors.append(
                        {
                            "code": "incomplete-priority-branch-record",
                            "path": rel,
                            "detail": label,
                        }
                    )

        on_complete = fields.get("on_complete", "")
        if on_complete and not ON_COMPLETE_RE.fullmatch(on_complete):
            errors.append(
                {
                    "code": "ambiguous-on-complete",
                    "path": rel,
                    "detail": on_complete,
                }
            )

        for heading in ("Allowed scope", "Excluded scope", "Validation"):
            if not has_heading(text, heading):
                errors.append(
                    {
                        "code": "missing-plan-section",
                        "path": rel,
                        "detail": heading,
                    }
                )

        current_task = fields.get("current_task_id", "")
        milestones = [
            (task.strip(), status.lower())
            for task, status in MILESTONE_ROW_RE.findall(text)
        ]
        in_progress = [task for task, status in milestones if status == "in_progress"]
        if len(in_progress) != 1:
            errors.append(
                {
                    "code": "invalid-in-progress-count",
                    "path": rel,
                    "detail": f"expected 1, found {len(in_progress)}",
                }
            )
        if current_task and not any(task == current_task for task, _ in milestones):
            errors.append(
                {
                    "code": "current-task-not-in-milestones",
                    "path": rel,
                    "detail": current_task,
                }
            )
        elif current_task and not any(
            task == current_task and status == "in_progress"
            for task, status in milestones
        ):
            errors.append(
                {
                    "code": "current-task-not-in-progress",
                    "path": rel,
                    "detail": current_task,
                }
            )

        navigation = validate_plan_navigation(rel, text, fields, errors)
        if navigation is not None:
            plan_navigation.append(navigation)

    for rel in undeclared_roadmap_authority:
        target = errors if active_plans else warnings
        target.append(
            {
                "code": "roadmap-authority-undeclared",
                "path": rel,
                "detail": "declare execution_authority: none when the roadmap coexists with execution plans",
            }
        )

    for rel in undeclared_checkpoint_authority:
        target = errors if active_plans else warnings
        target.append(
            {
                "code": "checkpoint-authority-undeclared",
                "path": rel,
                "detail": "declare execution_authority: none",
            }
        )

    if len(active_plans) > 1:
        errors.append(
            {
                "code": "multiple-active-plans",
                "path": ".",
                "detail": ", ".join(active_plans),
            }
        )

    root_agents = root / "AGENTS.md"
    if active_plans and root_agents.exists():
        try:
            agent_text = root_agents.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeDecodeError):
            agent_text = ""
        missing_routes = []
        if "plans.md" not in agent_text:
            missing_routes.append("PLANS.md")
        if roadmap_paths and "roadmap" not in agent_text:
            missing_routes.append("roadmap")
        if checkpoint_paths and "current.md" not in agent_text:
            missing_routes.append("docs/work/current.md")
        if missing_routes:
            errors.append(
                {
                    "code": "missing-plan-authority-routing",
                    "path": "AGENTS.md",
                    "detail": ", ".join(missing_routes),
                }
            )
        has_change_routing = all(
            label in agent_text for label in ALLOWED_CHANGE_CLASSES
        )
        if not has_change_routing:
            errors.append(
                {
                    "code": "missing-requirement-change-routing",
                    "path": "AGENTS.md",
                    "detail": ", ".join(sorted(ALLOWED_CHANGE_CLASSES)),
                }
            )
        if "subagent" not in agent_text and "子代理" not in agent_text:
            errors.append(
                {
                    "code": "missing-subagent-authority-routing",
                    "path": "AGENTS.md",
                    "detail": "state that delegated work cannot broaden scope or select roadmap work without explicit authority",
                }
            )

    info.append(
        {
            "code": "planning-authority",
            "active_plans": active_plans,
            "roadmaps": roadmap_paths,
            "checkpoints": checkpoint_paths,
            "noncanonical_planning": noncanonical_planning_paths,
            "plan_navigation": plan_navigation,
            "artifacts": [
                path.relative_to(root).as_posix()
                for path, _, _ in planning_records
            ],
        }
    )


def validate_command_claims(
    root: Path,
    files: list[Path],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    managers, scripts = repository_package_facts(root)
    expected_manager = next(iter(managers)) if len(managers) == 1 else None
    seen: set[tuple[str, str, str]] = set()

    if len(managers) > 1:
        warnings.append(
            {
                "code": "multiple-package-managers",
                "path": ".",
                "detail": ", ".join(sorted(managers)),
            }
        )

    for path in files:
        rel = path.relative_to(root).as_posix()
        if not (
            rel == "README.md"
            or rel == "PLANS.md"
            or path.name in {"AGENTS.md", "AGENTS.override.md"}
            or rel.startswith("docs/")
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for snippet in command_snippets(text):
            claim = parse_package_command(snippet)
            if claim is not None:
                manager, script = claim
                if expected_manager and manager != expected_manager:
                    key = ("package-manager-mismatch", rel, snippet)
                    if key not in seen:
                        errors.append(
                            {
                                "code": key[0],
                                "path": rel,
                                "detail": f"{snippet}; repository evidence selects {expected_manager}",
                            }
                        )
                        seen.add(key)
                if script and scripts and script not in scripts:
                    key = ("unknown-package-script", rel, snippet)
                    if key not in seen:
                        warnings.append(
                            {
                                "code": key[0],
                                "path": rel,
                                "detail": f"{snippet}; script '{script}' is absent from package manifests",
                            }
                        )
                        seen.add(key)
                continue

            manual_command = manual_command_claim(snippet)
            if manual_command:
                key = ("command-needs-manual-verification", rel, snippet)
                if key not in seen:
                    warnings.append(
                        {
                            "code": key[0],
                            "path": rel,
                            "detail": (
                                f"{snippet}; {manual_command} commands are inventoried "
                                "but not mechanically proven by this validator"
                            ),
                        }
                    )
                    seen.add(key)

        if path.name in {"AGENTS.md", "AGENTS.override.md"}:
            vague = [label for label, pattern in VAGUE_AGENT_PATTERNS.items() if pattern.search(text)]
            if vague:
                warnings.append(
                    {
                        "code": "vague-agents-guidance",
                        "path": rel,
                        "detail": ", ".join(vague),
                    }
                )


def validate(root: Path, profile: str) -> dict[str, object]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    info: list[dict[str, object]] = []

    for rel in PROFILE_REQUIRED[profile]:
        if not (root / rel).exists():
            errors.append({"code": "missing-required", "path": rel})

    files = markdown_files(root)
    scan = getattr(markdown_files, "last_scan", {})
    if scan.get("truncated"):
        warnings.append(
            {
                "code": "markdown-scan-truncated",
                "path": ".",
                "detail": (
                    f"bounded scan reached {scan.get('file_count', 0)} files or "
                    f"{scan.get('total_bytes', 0)} bytes; use targeted review for omitted files"
                ),
            }
        )
    root_literals = {
        str(root),
        root.as_posix(),
        str(root).replace("\\", "/"),
    }
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            if path.stat().st_size > MAX_MARKDOWN_FILE_BYTES:
                warnings.append(
                    {
                        "code": "oversized-markdown-needs-targeted-review",
                        "path": rel,
                        "detail": f"file exceeds {MAX_MARKDOWN_FILE_BYTES} bytes",
                    }
                )
                continue
        except OSError:
            pass
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append({"code": "unreadable-markdown", "path": rel, "detail": str(exc)})
            continue

        placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
        if placeholders:
            errors.append(
                {
                    "code": "unresolved-placeholders",
                    "path": rel,
                    "detail": ", ".join(placeholders[:20]),
                }
            )

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append({"code": "possible-secret", "path": rel, "detail": label})

        personal_paths = sorted(set(PERSONAL_PATH_RE.findall(text)))
        if personal_paths:
            warnings.append(
                {
                    "code": "personal-absolute-path",
                    "path": rel,
                    "detail": ", ".join(personal_paths[:5]),
                }
            )
        if any(literal and literal in text for literal in root_literals):
            warnings.append(
                {
                    "code": "repository-absolute-path",
                    "path": rel,
                    "detail": (
                        "use repository-relative durable context; keep the "
                        "host-local absolute path in a task-local handoff"
                    ),
                }
            )

        for raw_target in MARKDOWN_LINK_RE.findall(text):
            target = local_link_target(path, root, raw_target)
            if target is None:
                continue
            try:
                target.relative_to(root)
            except ValueError:
                warnings.append(
                    {"code": "link-outside-project", "path": rel, "detail": raw_target}
                )
                continue
            if not target.exists():
                errors.append({"code": "broken-link", "path": rel, "detail": raw_target})

    validate_command_claims(root, files, errors, warnings)
    validate_planning_authority(root, files, errors, warnings, info)

    agent_files = [
        path
        for path in files
        if path.name in {"AGENTS.md", "AGENTS.override.md"}
    ]
    for path in agent_files:
        size = path.stat().st_size
        rel = path.relative_to(root).as_posix()
        if size > 12_000:
            warnings.append(
                {
                    "code": "large-agents-file",
                    "path": rel,
                    "detail": f"{size} bytes; move detail to docs or skill references",
                }
            )

    agent_dirs = {path.parent for path in agent_files}
    for directory in sorted(agent_dirs):
        ordinary = directory / "AGENTS.md"
        override = directory / "AGENTS.override.md"
        if ordinary.exists() and override.exists():
            warnings.append(
                {
                    "code": "shadowed-agents-file",
                    "path": ordinary.relative_to(root).as_posix(),
                    "detail": f"{override.name} takes precedence in the same directory",
                }
            )

    nested_agents = [
        path.relative_to(root).as_posix()
        for path in agent_files
        if path.parent != root
    ]
    if nested_agents:
        info.append({"code": "nested-agents-review", "paths": nested_agents})

    root_agents = root / "AGENTS.md"
    if root_agents.exists():
        try:
            root_lines = substantive_lines(root_agents.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            root_lines = set()
        for path in agent_files:
            if path.parent == root:
                continue
            try:
                local_lines = substantive_lines(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            repeated = sorted(root_lines & local_lines)
            if len(repeated) >= 2 and len(repeated) / max(len(local_lines), 1) >= 0.4:
                warnings.append(
                    {
                        "code": "duplicated-agents-guidance",
                        "path": path.relative_to(root).as_posix(),
                        "detail": f"{len(repeated)} substantive lines repeat root AGENTS.md",
                    }
                )

    advanced_surfaces = []
    for rel in (
        ".codex/config.toml",
        ".codex/hooks.json",
        ".codex/rules",
        ".codex/agents",
        ".agents/skills",
    ):
        if (root / rel).exists():
            advanced_surfaces.append(rel)
    config_path = root / ".codex" / "config.toml"
    if config_path.exists():
        try:
            if tomllib is None:
                raise ValueError("TOML validation requires Python 3.11+")
            tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(
                {
                    "code": "invalid-codex-config",
                    "path": ".codex/config.toml",
                    "detail": str(exc),
                }
            )
    hooks_path = root / ".codex" / "hooks.json"
    if hooks_path.exists():
        try:
            json.loads(hooks_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(
                {
                    "code": "invalid-hooks-json",
                    "path": ".codex/hooks.json",
                    "detail": str(exc),
                }
            )
    if advanced_surfaces:
        warnings.append(
            {
                "code": "advanced-surfaces-require-semantic-review",
                "path": ".",
                "detail": (
                    "syntax and inventory checks do not prove permissions, side effects, "
                    "hook behavior, rule coverage, agent quality, or MCP trust boundaries"
                ),
            }
        )
    elif profile == "advanced":
        warnings.append(
            {
                "code": "advanced-profile-without-advanced-surfaces",
                "path": ".",
                "detail": "use standard unless a demonstrated need justifies an advanced surface",
            }
        )
    info.append({"code": "advanced-surfaces", "paths": advanced_surfaces})

    return {
        "root": str(root),
        "profile": profile,
        "ok": not errors,
        "summary": {
            "markdown_files": len(files),
            "markdown_bytes": scan.get("total_bytes", 0),
            "scan_truncated": bool(scan.get("truncated")),
            "agent_files": len(agent_files),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", help="Project root to validate")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_REQUIRED),
        default="minimal",
    )
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    result = validate(root, args.profile)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
