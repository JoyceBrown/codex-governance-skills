#!/usr/bin/env python3
"""Project-scoped projection and retrieval for the durable-context Obsidian vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from context_state import (
    automatic,
    atomic_write,
    plan_navigation_view,
    read_changes,
    read_excerpt,
    read_json,
    reconcile,
    require_text,
    sha256_text,
    utc_now,
    verify,
)


DEFAULT_VAULT = Path(
    os.environ.get(
        "DURABLE_CONTEXT_VAULT",
        str(Path.home() / "Obsidian" / "上下文系统"),
    )
)
VAULT_DIRS = (
    "00-首页",
    "01-项目",
    "02-决策",
    "03-发现",
    "04-交接",
    "05-长期记忆",
    "06-收件箱",
    "99-模板",
    "系统",
)
REQUIRED_VAULT_FILES = (
    "00-首页/上下文系统.md",
    "00-首页/项目索引.md",
    "系统/config.json",
)
BASE_FILE_CONTENT = {
    "00-首页/上下文系统.md": "# 上下文系统\n\n由 durable-context 管理的 Obsidian 上下文 Vault。项目账本仍是事实源。\n",
    "00-首页/项目索引.md": "# 项目索引\n\n暂无已同步项目。\n",
}


def resolve_vault(value: str) -> Path:
    vault = Path(value).expanduser().resolve() if value else DEFAULT_VAULT.resolve()
    return vault


@contextmanager
def vault_lock(vault: Path):
    vault.mkdir(parents=True, exist_ok=True)
    lock_path = vault / ".durable-context.lock"
    handle = lock_path.open("a+b")
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


def ensure_vault(vault: Path) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    for name in VAULT_DIRS:
        (vault / name).mkdir(parents=True, exist_ok=True)

    config = vault / "系统/config.json"
    if not config.exists():
        atomic_write(
            config,
            json.dumps(
                {
                    "version": 1,
                    "vault_name": vault.name,
                    "managed_by": "durable-context",
                    "source_of_truth": "project-local .agent-context",
                    "auto_sync_policy": "checkpoint-and-finish-only",
                    "auto_write_policy": "verified-or-user-requested-only",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
    for relative, content in BASE_FILE_CONTENT.items():
        path = vault / relative
        if not path.exists():
            atomic_write(path, content)


def safe_name(value: str, fallback: str = "memory") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    if normalized:
        return normalized[:80]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{fallback}-{digest}"


def project_slug(project_root: Path) -> str:
    resolved = project_root.resolve()
    digest = hashlib.sha1(str(resolved).lower().encode("utf-8")).hexdigest()[:8]
    return f"{safe_name(resolved.name, 'project')}-{digest}"


def frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(("---", ""))
    return "\n".join(lines)


def write_managed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, content.rstrip() + "\n")


def read_frontmatter(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        try:
            values[key.strip()] = json.loads(raw.strip())
        except json.JSONDecodeError:
            values[key.strip()] = raw.strip().strip('"')
    return values


def normalize_body(value: str) -> str:
    return value.rstrip() + "\n"


def read_markdown_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    return read_frontmatter(path), "".join(lines[end + 1 :])


def managed_page(metadata: dict[str, Any], body: str) -> str:
    normalized = normalize_body(body)
    values = dict(metadata)
    values["content_hash"] = sha256_text(normalized)
    return frontmatter(values) + normalized


def archive_projection(project_dir: Path, new_task_id: str) -> str:
    current = read_frontmatter(project_dir / "项目上下文.md")
    old_task_id = str(current.get("task_id", "")).strip()
    if not old_task_id or old_task_id == new_task_id:
        return ""
    history_dir = project_dir / "历史" / old_task_id
    suffix = 1
    candidate = history_dir
    while candidate.exists():
        candidate = project_dir / "历史" / f"{old_task_id}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=True)
    for path in project_dir.rglob("*"):
        relative = path.relative_to(project_dir)
        if "历史" in relative.parts or not path.is_file():
            continue
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    write_managed(
        candidate / "归档说明.md",
        frontmatter(
            {
                "type": "project-archive",
                "task_id": old_task_id,
                "status": "superseded",
                "managed_by": "durable-context",
                "archived_at": utc_now(),
            }
        )
        + "# 历史项目投影\n\n"
        + "该投影已被新的任务状态替代，只用于追溯，不应作为当前要求使用。\n",
    )
    managed_history = project_dir / "要求历史"
    if managed_history.is_dir():
        shutil.rmtree(managed_history)
    return str(candidate)


def write_requirement_history(
    project_dir: Path,
    slug: str,
    manifest: dict[str, Any],
    changes: list[dict[str, Any]],
    current_requirements: str,
    consistency_status: str,
) -> dict[int, str]:
    links: dict[int, str] = {}
    history_root = project_dir / "要求历史"
    if history_root.is_dir():
        shutil.rmtree(history_root)
    history_root.mkdir(parents=True, exist_ok=True)
    current_revision = int(manifest.get("requirements_revision", 0))
    for entry in changes:
        if entry.get("kind") == "task_started":
            revision = int(entry.get("revision", 0))
        elif entry.get("kind") == "requirement_change" and isinstance(entry.get("after_revision"), int):
            revision = entry["after_revision"]
        else:
            continue
        snapshot = entry.get("requirements_after")
        if not isinstance(snapshot, str):
            continue
        relative = f"要求历史/revision-{revision}.md"
        body = f"# 要求 Revision {revision}\n\n"
        body += f"变更摘要：{entry.get('summary', '')}\n\n"
        body += snapshot
        page = managed_page(
            {
                "type": "requirements-snapshot",
                "task_id": manifest.get("task_id", "unknown"),
                "revision": revision,
                "status": "current" if revision == current_revision else "superseded",
                "consistency": consistency_status,
                "source": "changes.jsonl",
                "requirements_hash": sha256_text(snapshot),
                "managed_by": "durable-context",
                "generated": True,
            },
            body,
        )
        write_managed(project_dir / relative, page)
        links[revision] = f"[[01-项目/{slug}/{relative[:-3]}|requirements revision {revision}]]"
    if current_revision not in links:
        relative = f"要求历史/revision-{current_revision}.md"
        body = f"# 要求 Revision {current_revision}\n\n"
        body += "历史事件缺少完整快照；本页保存同步时的当前要求。\n\n"
        body += current_requirements
        page = managed_page(
            {
                "type": "requirements-snapshot",
                "task_id": manifest.get("task_id", "unknown"),
                "revision": current_revision,
                "status": "current",
                "consistency": consistency_status,
                "source": "current-requirements-fallback",
                "requirements_hash": sha256_text(current_requirements),
                "managed_by": "durable-context",
                "generated": True,
            },
            body,
        )
        write_managed(project_dir / relative, page)
        links[current_revision] = f"[[01-项目/{slug}/{relative[:-3]}|requirements revision {current_revision}]]"
    return links


def render_change_log(
    manifest: dict[str, Any],
    changes: list[dict[str, Any]],
    requirement_links: dict[int, str],
) -> str:
    body = "# 变更日志\n\n"
    body += "本页由项目账本的追加式 `changes.jsonl` 投影生成。\n\n"
    for entry in changes:
        kind = entry.get("kind", "unknown")
        at = entry.get("at", "unknown")
        summary = entry.get("summary", "")
        category = entry.get("category", "")
        revision = entry.get("after_revision", entry.get("revision", ""))
        link = requirement_links.get(revision, "") if isinstance(revision, int) else ""
        suffix = f" - {link}" if link else ""
        body += f"- `{at}` `{kind}` `{category}` revision `{revision}`: {summary}{suffix}\n"
    if not changes:
        body += "暂无变更记录。\n"
    return managed_page(
        {
            "type": "change-log",
            "task_id": manifest.get("task_id", "unknown"),
            "requirements_revision": manifest.get("requirements_revision", 0),
            "managed_by": "durable-context",
            "generated": True,
        },
        body,
    )


def render_consistency(consistency: dict[str, Any], task_id: str) -> str:
    body = "# 一致性检查\n\n"
    errors = consistency.get("errors", [])
    warnings = consistency.get("warnings", [])
    if not errors and not warnings:
        body += "当前项目账本结构和检查点状态一致。\n"
    if errors:
        body += "## 错误\n\n" + "\n".join(f"- {item}" for item in errors) + "\n"
    if warnings:
        body += "## 警告\n\n" + "\n".join(f"- {item}" for item in warnings) + "\n"
    body += "\n旧记忆必须重新核对当前代码、测试和用户最新要求。\n"
    return managed_page(
        {
            "type": "consistency-check",
            "task_id": task_id,
            "status": "verified" if consistency.get("valid") and not consistency.get("warnings") else "needs-review",
            "consistency": "verified" if consistency.get("valid") and not consistency.get("warnings") else "needs-review",
            "managed_by": "durable-context",
            "generated": True,
        },
        body,
    )


def _sync_project(project_root: Path, vault: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    context_dir = project_root / ".agent-context"
    if not context_dir.is_dir():
        raise ValueError(f"project ledger does not exist: {context_dir}")

    errors = verify(context_dir, expected_root=project_root)
    if errors:
        raise ValueError("project ledger is invalid: " + "; ".join(errors))

    ensure_vault(vault)
    manifest = read_json(context_dir / "manifest.json")
    registry_path = vault / VAULT_DIRS[-1] / "projects.json"
    registry: dict[str, Any] = {"version": 1, "projects": []}
    if registry_path.exists():
        try:
            parsed = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict) and isinstance(parsed.get("projects"), list):
                registry = parsed
            else:
                raise ValueError("system project registry must contain an object with a projects list")
        except json.JSONDecodeError as exc:
            raise ValueError(f"refusing to overwrite corrupted project registry: {exc}") from exc
    slug = project_slug(project_root)
    project_dir = vault / "01-项目" / slug
    project_dir.mkdir(parents=True, exist_ok=True)
    updated = manifest.get("updated_at", utc_now())
    task = str(manifest.get("task", project_root.name))
    status = str(manifest.get("status", "unknown"))
    checkpoint = int(manifest.get("checkpoint", 0))
    consistency = reconcile(context_dir, expected_root=project_root)
    if not consistency["valid"] or consistency["warnings"]:
        problems = consistency["errors"] + consistency["warnings"]
        raise ValueError("refusing to sync an inconsistent project ledger: " + "; ".join(problems))
    consistency_status = "verified"
    navigation = plan_navigation_view(project_root)
    navigation_metadata: dict[str, Any] = {}
    if navigation.get("configured") and navigation.get("valid"):
        navigation_metadata = {
            "plan_route_id": navigation.get("route_id"),
            "plan_route_coordinate": navigation.get("current_route_coordinate"),
            "plan_current_task_id": navigation.get("current_task_id"),
            "plan_continuity_parent_task_id": navigation.get("continuity_parent_task_id"),
            "plan_source_hash": navigation.get("source_hash"),
            "plan_navigation_authority": navigation.get("authority"),
        }
    archived_projection = archive_projection(project_dir, str(manifest.get("task_id", "unknown")))

    handoff = read_excerpt(context_dir / "handoff.md", 12000)
    requirements = (context_dir / "requirements.md").read_text(encoding="utf-8")
    requirements_hash = sha256_text(requirements)
    decisions = read_excerpt(context_dir / "decisions.md", 16000)
    findings = read_excerpt(context_dir / "findings.md", 16000)
    changes = read_changes(context_dir, maximum=100000)
    requirement_links = write_requirement_history(
        project_dir,
        slug,
        manifest,
        changes,
        requirements,
        consistency_status,
    )
    base = {
        "project": project_root.name,
        "project_root": project_root.as_posix(),
        "task_id": manifest.get("task_id", "unknown"),
        "status": status,
        "checkpoint": checkpoint,
        "requirements_revision": manifest.get("requirements_revision", 0),
        "consistency": consistency_status,
        "requirements_hash": requirements_hash,
        "source": "local-ledger",
        "managed_by": "durable-context",
        "updated": updated,
    }

    project_body = f"# {task}\n\n"
    project_body += "This page is an automatically generated projection. The local ledger remains authoritative.\n\n"
    project_body += f"## Current Requirements\n\n[[01-项目/{slug}/当前要求|Open the canonical current requirements projection.]]\n\n"
    project_body += "## Current Handoff\n\n"
    project_body += handoff
    project_body += "\n\n## Consistency\n\nNo pending consistency warnings.\n"
    if navigation.get("configured") and navigation.get("valid"):
        project_body += "\n## Plan Navigation\n\n"
        project_body += "Read-only projection from the active root `PLANS.md`; it does not authorize work.\n\n"
        project_body += f"- Route: `{navigation.get('route_id')}`\n"
        project_body += f"- Coordinate: `{navigation.get('current_route_coordinate')}`\n"
        project_body += f"- Plan task: `{navigation.get('current_task_id')}`\n"
        if navigation.get("continuity_parent_task_id"):
            project_body += f"- Continuity parent: `{navigation.get('continuity_parent_task_id')}`\n"
        project_body += f"- Source hash: `{navigation.get('source_hash')}`\n"
    elif navigation.get("configured"):
        project_body += "\n## Plan Navigation\n\n"
        project_body += "Navigation metadata was not projected because `PLANS.md` failed validation.\n\n"
        project_body += "\n".join(f"- {item}" for item in navigation.get("errors", [])) + "\n"
    project_body += "\n## Mirrors\n\n"
    project_body += f"- [[01-项目/{slug}/决策镜像|Decision mirror]]\n"
    project_body += f"- [[01-项目/{slug}/发现镜像|Finding mirror]]\n"
    project_body += f"- [[01-项目/{slug}/交接|Handoff mirror]]\n"
    project_body += f"- [[01-项目/{slug}/当前要求|Current requirements]]\n"
    project_body += f"- [[01-项目/{slug}/变更日志|Change log]]\n"
    project_body += f"- [[01-项目/{slug}/一致性检查|Consistency check]]\n"
    if archived_projection:
        project_body += f"\nPrevious task projection archived at `{archived_projection}`.\n"
    project_page = managed_page({"type": "project-context", **base, **navigation_metadata}, project_body)
    write_managed(project_dir / "项目上下文.md", project_page)

    mirror_base = {**base, "generated": True}
    write_managed(
        project_dir / "当前要求.md",
        managed_page(
            {"type": "requirements-current", **mirror_base},
            "# 当前要求\n\n" + requirements,
        ),
    )
    write_managed(
        project_dir / "决策镜像.md",
        managed_page(
            {"type": "decision-mirror", **mirror_base},
            "# 决策镜像\n\n"
            + "来源：项目账本 `decisions.md`。请勿把本页当作独立事实源。\n\n"
            + decisions,
        ),
    )
    write_managed(
        project_dir / "发现镜像.md",
        managed_page(
            {"type": "finding-mirror", **mirror_base},
            "# 发现镜像\n\n"
            + "来源：项目账本 `findings.md`。请重新核对当前代码和测试。\n\n"
            + findings,
        ),
    )
    write_managed(
        project_dir / "交接.md",
        managed_page(
            {"type": "handoff", **mirror_base},
            "# 交接镜像\n\n"
            + "来源：项目账本 `handoff.md`。\n\n"
            + handoff,
        ),
    )
    write_managed(project_dir / "变更日志.md", render_change_log(manifest, changes, requirement_links))
    write_managed(
        project_dir / "一致性检查.md",
        render_consistency(consistency, str(manifest.get("task_id", "unknown"))),
    )

    projects = {item.get("slug"): item for item in registry["projects"] if isinstance(item, dict) and item.get("slug")}
    projects[slug] = {
        "slug": slug,
        "name": project_root.name,
        "root": project_root.as_posix(),
        "task": task,
        "status": status,
        "checkpoint": checkpoint,
        "task_id": manifest.get("task_id", "unknown"),
        "requirements_revision": manifest.get("requirements_revision", 0),
        "consistency": base["consistency"],
        "requirements_hash": requirements_hash,
        "updated": updated,
        "synced_at": utc_now(),
    }
    if navigation_metadata:
        projects[slug].update(navigation_metadata)
    registry["projects"] = sorted(projects.values(), key=lambda item: (str(item.get("name", "")).lower(), item["slug"]))
    atomic_write(registry_path, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")

    index_lines = [
        "---",
        "type: project-index",
        "managed_by: durable-context",
        "generated: true",
        "---",
        "",
        "# 项目索引",
        "",
        "本页由 durable-context 自动维护；项目账本仍是事实源。",
        "",
    ]
    for item in registry["projects"]:
        index_lines.append(
            f"- [[01-项目/{item['slug']}/项目上下文|{item['name']}]] - {item['status']} - checkpoint {item['checkpoint']}"
        )
    write_managed(vault / "00-首页/项目索引.md", "\n".join(index_lines))
    result = {
        "vault": str(vault),
        "project": project_root.name,
        "slug": slug,
        "task_id": manifest.get("task_id", "unknown"),
        "status": status,
        "checkpoint": checkpoint,
        "requirements_revision": manifest.get("requirements_revision", 0),
        "consistency": base["consistency"],
        "archived_projection": archived_projection,
    }
    result["plan_navigation"] = {
        "configured": bool(navigation.get("configured")),
        "valid": bool(navigation.get("valid")),
    }
    if navigation_metadata:
        result["plan_navigation"].update(navigation_metadata)
    elif navigation.get("configured"):
        result["plan_navigation"]["errors"] = list(navigation.get("errors", []))
    return result


def sync_project(project_root: Path, vault: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    with vault_lock(vault):
        return _sync_project(project_root, vault)


def verify_vault(vault: Path) -> list[str]:
    errors: list[str] = []
    for name in VAULT_DIRS:
        if not (vault / name).is_dir():
            errors.append(f"missing directory: {name}")
    for name in REQUIRED_VAULT_FILES:
        if not (vault / name).is_file():
            errors.append(f"missing required file: {name}")
    config = vault / "系统/config.json"
    if config.is_file():
        try:
            parsed = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                errors.append("系统/config.json must contain an object")
        except json.JSONDecodeError as exc:
            errors.append(f"invalid 系统/config.json: {exc}")

    project_root = vault / "01-项目"
    current_pages = sorted(project_root.glob("*/项目上下文.md")) if project_root.is_dir() else []
    current_by_slug: dict[str, dict[str, Any]] = {}
    seen_roots: dict[str, str] = {}
    seen_task_ids: dict[str, str] = {}
    for page in current_pages:
        slug = page.parent.name
        metadata, body = read_markdown_document(page)
        current_by_slug[slug] = metadata
        if metadata.get("content_hash") != sha256_text(body):
            errors.append(f"current project page content hash mismatch: {page}")
        if metadata.get("type") != "project-context":
            errors.append(f"invalid current project page type: {page}")
        task_id = str(metadata.get("task_id", "")).strip()
        project_path = str(metadata.get("project_root", "")).strip().casefold()
        if not task_id:
            errors.append(f"current project page is missing task_id: {page}")
        elif task_id in seen_task_ids:
            errors.append(f"duplicate current task_id: {task_id}")
        else:
            seen_task_ids[task_id] = slug
        if not project_path:
            errors.append(f"current project page is missing project_root: {page}")
        elif project_path in seen_roots:
            errors.append(f"duplicate current project_root: {metadata.get('project_root')}")
        else:
            seen_roots[project_path] = slug
        requirements_page = page.parent / "当前要求.md"
        consistency_page = page.parent / "一致性检查.md"
        if not requirements_page.is_file():
            errors.append(f"missing current requirements projection: {requirements_page}")
        else:
            requirement_metadata, requirement_body = read_markdown_document(requirements_page)
            if requirement_metadata.get("content_hash") != sha256_text(requirement_body):
                errors.append(f"requirements content hash mismatch: {requirements_page}")
            if requirement_metadata.get("task_id") != metadata.get("task_id"):
                errors.append(f"requirements task_id mismatch: {requirements_page}")
            if requirement_metadata.get("requirements_revision") != metadata.get("requirements_revision"):
                errors.append(f"requirements revision mismatch: {requirements_page}")
            if requirement_metadata.get("requirements_hash") != metadata.get("requirements_hash"):
                errors.append(f"requirements canonical hash mismatch: {requirements_page}")
        if not consistency_page.is_file():
            errors.append(f"missing consistency projection: {consistency_page}")
        revision = metadata.get("requirements_revision")
        snapshot_page = page.parent / "要求历史" / f"revision-{revision}.md"
        if not snapshot_page.is_file():
            errors.append(f"missing current requirements snapshot: {snapshot_page}")
        else:
            snapshot_metadata, snapshot_body = read_markdown_document(snapshot_page)
            if snapshot_metadata.get("content_hash") != sha256_text(snapshot_body):
                errors.append(f"current requirements snapshot content hash mismatch: {snapshot_page}")
            if snapshot_metadata.get("status") != "current":
                errors.append(f"current requirements snapshot has wrong status: {snapshot_page}")
            if snapshot_metadata.get("task_id") != metadata.get("task_id"):
                errors.append(f"current requirements snapshot task_id mismatch: {snapshot_page}")
            if snapshot_metadata.get("requirements_hash") != metadata.get("requirements_hash"):
                errors.append(f"current requirements snapshot canonical hash mismatch: {snapshot_page}")
        for generated_page in page.parent.glob("*.md"):
            generated_metadata, generated_body = read_markdown_document(generated_page)
            if generated_metadata.get("generated") and generated_metadata.get("managed_by") == "durable-context":
                if generated_metadata.get("content_hash") != sha256_text(generated_body):
                    errors.append(f"generated page content hash mismatch: {generated_page}")

    registry_path = vault / VAULT_DIRS[-1] / "projects.json"
    registry_projects: dict[str, dict[str, Any]] = {}
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            projects = registry.get("projects", []) if isinstance(registry, dict) else []
            if not isinstance(projects, list):
                errors.append("系统/projects.json projects must be a list")
                projects = []
            for item in projects:
                if not isinstance(item, dict) or not item.get("slug"):
                    errors.append("系统/projects.json contains an invalid project entry")
                    continue
                slug = str(item["slug"])
                if slug in registry_projects:
                    errors.append(f"duplicate registry slug: {slug}")
                registry_projects[slug] = item
        except json.JSONDecodeError as exc:
            errors.append(f"invalid 系统/projects.json: {exc}")
    elif current_pages:
        errors.append("missing 系统/projects.json for current project pages")

    if set(registry_projects) != set(current_by_slug):
        missing_registry = sorted(set(current_by_slug) - set(registry_projects))
        orphan_registry = sorted(set(registry_projects) - set(current_by_slug))
        if missing_registry:
            errors.append("current projects missing from registry: " + ", ".join(missing_registry))
        if orphan_registry:
            errors.append("registry projects missing current pages: " + ", ".join(orphan_registry))
    for slug, metadata in current_by_slug.items():
        item = registry_projects.get(slug)
        if not item:
            continue
        for key in (
            "task_id",
            "status",
            "requirements_revision",
            "consistency",
            "requirements_hash",
            "plan_route_id",
            "plan_route_coordinate",
            "plan_current_task_id",
            "plan_continuity_parent_task_id",
            "plan_source_hash",
            "plan_navigation_authority",
        ):
            if item.get(key) != metadata.get(key):
                errors.append(f"registry {key} mismatch for {slug}")
        if str(item.get("root", "")).casefold() != str(metadata.get("project_root", "")).casefold():
            errors.append(f"registry root mismatch for {slug}")

    for archive_note in project_root.glob("*/历史/*/归档说明.md") if project_root.is_dir() else []:
        metadata = read_frontmatter(archive_note)
        if metadata.get("status") != "superseded":
            errors.append(f"archive is not marked superseded: {archive_note}")
    return errors


def search_vault(
    vault: Path,
    query: str,
    maximum: int,
    include_history: bool = False,
    include_unverified: bool = False,
    project_root: Path | None = None,
    max_chars: int = 12000,
) -> list[dict[str, Any]]:
    needle = require_text(query, "query").casefold()
    if project_root is None:
        return []
    project_root = project_root.resolve()
    context_dir = project_root / ".agent-context"
    try:
        scope_errors = verify(context_dir, expected_root=project_root)
        consistency = reconcile(context_dir, expected_root=project_root)
        manifest = read_json(context_dir / "manifest.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    if scope_errors or (consistency.get("errors") or consistency.get("warnings")):
        return []
    scope_root = project_root.as_posix().casefold()
    current_task_id = str(manifest.get("task_id", ""))
    max_chars = max(1000, int(max_chars))
    candidates: list[dict[str, Any]] = []
    for path in sorted(vault.rglob("*.md")):
        if ".obsidian" in path.parts:
            continue
        relative = path.relative_to(vault)
        is_history = "历史" in relative.parts
        metadata, body = read_markdown_document(path)
        if metadata.get("managed_by") != "durable-context":
            continue
        if str(metadata.get("project_root", "")).strip().casefold() != scope_root:
            continue
        if not include_history and str(metadata.get("task_id", "")) != current_task_id:
            continue
        status = str(metadata.get("status", "")).casefold()
        consistency = str(metadata.get("consistency", "")).casefold()
        content_hash_valid = bool(metadata.get("content_hash")) and metadata.get("content_hash") == sha256_text(body)
        if is_history and not include_history:
            continue
        if metadata.get("type") == "requirements-snapshot" and not include_history:
            continue
        if status in {"superseded", "archived"} and not include_history:
            continue
        if status in {"needs-review", "observed"} and not include_unverified:
            continue
        if consistency and consistency != "verified" and not include_unverified:
            continue
        if not content_hash_valid and not include_unverified:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        matches = [
            {"line": number, "text": line.strip()[:500]}
            for number, line in enumerate(lines, start=1)
            if needle in line.casefold()
        ]
        if matches:
            candidates.append(
                {
                    "file": str(path),
                    "type": metadata.get("type", ""),
                    "status": metadata.get("status", ""),
                    "task_id": metadata.get("task_id", ""),
                    "source": metadata.get("source", ""),
                    "consistency": metadata.get("consistency", ""),
                    "content_hash_valid": content_hash_valid,
                    "matches": matches[:20],
                }
            )
    priorities = {
        "requirements-current": 0,
        "project-context": 1,
        "handoff": 2,
        "decision-mirror": 3,
        "finding-mirror": 3,
        "change-log": 4,
        "consistency-check": 5,
    }
    candidates.sort(key=lambda item: (priorities.get(str(item.get("type", "")), 10), item["file"]))
    results: list[dict[str, Any]] = []
    seen_by_task: dict[str, set[str]] = {}
    used_chars = 0
    for candidate in candidates:
        task_id = str(candidate.get("task_id", ""))
        normalized_matches = {
            re.sub(r"[^\w\u4e00-\u9fff]+", " ", match["text"].casefold()).strip()
            for match in candidate["matches"]
            if match["text"].strip()
        }
        if task_id and normalized_matches and normalized_matches.issubset(seen_by_task.get(task_id, set())):
            continue
        if task_id:
            seen_by_task.setdefault(task_id, set()).update(normalized_matches)
        candidate_size = len(json.dumps(candidate, ensure_ascii=False))
        if results and used_chars + candidate_size > max_chars:
            break
        if not results and candidate_size > max_chars:
            candidate["matches"] = candidate["matches"][:1]
            candidate_size = len(json.dumps(candidate, ensure_ascii=False))
        results.append(candidate)
        used_chars += candidate_size
        if len(results) >= maximum:
            break
    return results


def remember(vault: Path, title: str, kind: str, content: str, scope: str, source: str, status: str, tags: str, force: bool) -> Path:
    roots = {
        "decision": "02-决策",
        "finding": "03-发现",
        "long-term": "05-长期记忆",
        "inbox": "06-收件箱",
    }
    if kind not in roots:
        raise ValueError(f"unsupported kind: {kind}")
    ensure_vault(vault)
    filename = safe_name(title) + ".md"
    path = vault / roots[kind] / filename
    if path.exists() and not force:
        raise ValueError(f"memory already exists: {path}; use force only for an intentional replacement")
    tag_values = [item.strip() for item in tags.split(",") if item.strip()]
    body = f"# {title}\n\n" + require_text(content, "content")
    metadata = {
        "type": kind,
        "scope": scope,
        "status": status,
        "source": source,
        "created": utc_now(),
        "tags": tag_values,
        "managed_by": "durable-context",
    }
    write_managed(path, managed_page(metadata, body))
    return path


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="obsidian-project-") as project_value, tempfile.TemporaryDirectory(
        prefix="obsidian-vault-"
    ) as vault_value:
        project = Path(project_value)
        vault = Path(vault_value)
        ledger = project / ".agent-context"
        automatic(project, ledger, "start", "Old searchable task", "", "", "", "", "active", 3000)
        old_requirements = (ledger / "requirements.md").read_text(encoding="utf-8").replace(
            "- [ ] Define the completion evidence.", "- [x] Define the completion evidence."
        )
        automatic(
            project,
            ledger,
            "change",
            "",
            "Self-test acceptance evidence recorded.",
            "Complete the old task.",
            "",
            "",
            "active",
            3000,
            category="acceptance",
            source="self-test",
            requirements=old_requirements,
        )
        automatic(project, ledger, "finish", "", "Old complete", "No action", "self-test", "", "active", 3000)
        sync_project(project, vault)
        automatic(project, ledger, "start", "Current task", "", "", "", "", "active", 3000)
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
        (project / "PLANS.md").write_text(valid_plan, encoding="utf-8")
        current = sync_project(project, vault)
        errors = verify_vault(vault)
        if errors:
            raise RuntimeError(f"vault verification failed: {errors}")
        current_pages = [
            path
            for path in vault.rglob("*.md")
            if read_frontmatter(path).get("type") == "project-context"
            and read_frontmatter(path).get("task_id") == current["task_id"]
        ]
        if not current_pages or not all("# Current Requirements" in path.read_text(encoding="utf-8") for path in current_pages):
            raise RuntimeError("current requirements are missing from the project projection")
        navigation_metadata = read_frontmatter(current_pages[0])
        if (
            current["plan_navigation"].get("plan_route_coordinate") != "R7:A3/B2"
            or navigation_metadata.get("plan_route_coordinate") != "R7:A3/B2"
            or len(str(navigation_metadata.get("plan_source_hash", ""))) != 64
        ):
            raise RuntimeError("valid plan navigation is missing from the project projection")
        requirement_pages = [
            path
            for path in vault.rglob("*.md")
            if read_frontmatter(path).get("type") == "requirements-current"
            and read_frontmatter(path).get("task_id") == current["task_id"]
        ]
        if len(requirement_pages) != 1 or "Current task" not in requirement_pages[0].read_text(encoding="utf-8"):
            raise RuntimeError("canonical current requirements projection is missing")
        if search_vault(vault, "Old searchable task", 20, project_root=project):
            raise RuntimeError("default search returned historical content")
        if not search_vault(vault, "Old searchable task", 20, include_history=True, project_root=project):
            raise RuntimeError("explicit historical search did not return archived content")
        current_hits = search_vault(vault, "Current task", 20, project_root=project)
        if any(item.get("type") == "requirements-snapshot" for item in current_hits):
            raise RuntimeError("default search returned a duplicate requirements snapshot")
        if len(current_hits) > 1:
            raise RuntimeError("default search returned duplicate current requirement content")
        if search_vault(vault, "Current task", 20):
            raise RuntimeError("search without an explicit project scope was not fail-closed")
        navigation_hits = search_vault(vault, "R7:A3/B2", 20, project_root=project)
        if not navigation_hits or navigation_hits[0].get("type") != "project-context":
            raise RuntimeError("valid plan navigation is not searchable in the project projection")

        registry_path = vault / VAULT_DIRS[-1] / "projects.json"
        navigation_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        navigation_registry["projects"][0]["plan_route_coordinate"] = "R7:A3/B9"
        atomic_write(registry_path, json.dumps(navigation_registry, ensure_ascii=False, indent=2) + "\n")
        if not any("registry plan_route_coordinate mismatch" in error for error in verify_vault(vault)):
            raise RuntimeError("vault verification missed a navigation registry mismatch")
        sync_project(project, vault)

        (project / "PLANS.md").write_text(valid_plan.replace("route_id: R7", "route_id: R8"), encoding="utf-8")
        invalid_navigation = sync_project(project, vault)
        invalid_page_metadata = read_frontmatter(current_pages[0])
        invalid_page_text = current_pages[0].read_text(encoding="utf-8")
        if (
            invalid_navigation["plan_navigation"].get("valid")
            or not invalid_navigation["plan_navigation"].get("errors")
            or "plan_route_coordinate" in invalid_page_metadata
            or "plan_source_hash" in invalid_page_metadata
            or "R7:A3/B2" in invalid_page_text
        ):
            raise RuntimeError("invalid plan navigation was projected as trusted metadata")
        if verify_vault(vault):
            raise RuntimeError("vault verification failed after rejecting invalid plan navigation")

        requirement_pages[0].write_text(
            requirement_pages[0].read_text(encoding="utf-8") + "\nTAMPERED\n",
            encoding="utf-8",
        )
        if not any("content hash mismatch" in error for error in verify_vault(vault)):
            raise RuntimeError("Vault verification did not detect a modified requirements page")
        sync_project(project, vault)

        task_path = ledger / "task.md"
        task_original = task_path.read_text(encoding="utf-8")
        task_path.write_text(task_original + "\n- pending execution change\n", encoding="utf-8")
        try:
            sync_project(project, vault)
        except ValueError as exc:
            refused_inconsistent = "refusing to sync an inconsistent" in str(exc)
        else:
            refused_inconsistent = False
        if not refused_inconsistent:
            raise RuntimeError("bridge accepted an inconsistent project ledger")
        task_path.write_text(task_original, encoding="utf-8")
        automatic(
            project,
            ledger,
            "checkpoint",
            "",
            "Restored task execution notes after the inconsistency probe.",
            "Continue the bridge regression.",
            "self-test",
            "",
            "active",
            3000,
        )

        registry_backup = registry_path.read_text(encoding="utf-8")
        registry_path.write_text("{corrupted", encoding="utf-8")
        try:
            sync_project(project, vault)
        except ValueError as exc:
            refused_corrupt_registry = "corrupted project registry" in str(exc)
            corrupt_registry_error = str(exc)
        else:
            refused_corrupt_registry = False
            corrupt_registry_error = "no error"
        if not refused_corrupt_registry:
            raise RuntimeError(f"bridge did not reject a corrupted project registry: {corrupt_registry_error}")
        registry_path.write_text(registry_backup, encoding="utf-8")
    print("obsidian bridge self-test passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="Obsidian vault path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="initialize vault directories")
    subparsers.add_parser("self-test", help="run isolated bridge regressions")
    sync_parser = subparsers.add_parser("sync", help="project local ledger projection")
    sync_parser.add_argument("--project-root", required=True)
    verify_parser = subparsers.add_parser("verify", help="validate vault structure")
    verify_parser.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)
    search_parser = subparsers.add_parser("search", help="search markdown memory")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--project-root", required=True, help=argparse.SUPPRESS)
    search_parser.add_argument("--max-results", type=int, default=20)
    search_parser.add_argument("--max-chars", type=int, default=12000, help=argparse.SUPPRESS)
    search_parser.add_argument("--include-history", action="store_true", help=argparse.SUPPRESS)
    search_parser.add_argument("--include-unverified", action="store_true", help=argparse.SUPPRESS)
    remember_parser = subparsers.add_parser("remember", help="write a curated memory")
    remember_parser.add_argument("--title", required=True)
    remember_parser.add_argument("--kind", choices=("decision", "finding", "long-term", "inbox"), default="inbox")
    remember_parser.add_argument("--content", required=True)
    remember_parser.add_argument("--scope", default="project")
    remember_parser.add_argument("--source", required=True)
    remember_parser.add_argument("--status", choices=("verified", "observed", "needs-review"), default="needs-review")
    remember_parser.add_argument("--tags", default="")
    remember_parser.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    vault = resolve_vault(args.vault)
    try:
        if args.command == "init":
            ensure_vault(vault)
            print(json.dumps({"vault": str(vault), "status": "initialized"}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "self-test":
            self_test()
            return 0
        if args.command == "sync":
            result = sync_project(Path(args.project_root), vault)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "verify":
            errors = verify_vault(vault)
            payload = {"vault": str(vault), "valid": not errors, "errors": errors}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if not errors else 1
        if args.command == "search":
            print(
                json.dumps(
                    search_vault(
                        vault,
                        args.query,
                        max(1, args.max_results),
                        include_history=args.include_history,
                        include_unverified=args.include_unverified,
                        project_root=Path(args.project_root),
                        max_chars=max(1000, args.max_chars),
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "remember":
            path = remember(vault, args.title, args.kind, args.content, args.scope, args.source, args.status, args.tags, args.force)
            print(json.dumps({"path": str(path), "status": "written"}, ensure_ascii=False, indent=2))
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
