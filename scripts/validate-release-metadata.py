#!/usr/bin/env python3
"""Enforce VERSION and CHANGELOG updates for protected contract changes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PREFIXES = (
    "schemas/",
    "scripts/validate-",
    "skills/project-agent-orchestrator/scripts/",
)
PROTECTED_EXACT = {
    "docs/composition.md",
    "docs/composition.schema.json",
    "docs/skill-capability-registry.json",
    "scripts/route-composition.py",
    "skills/project-agent-orchestrator/references/host-adapter.md",
}


def _normalise(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_protected(path: str) -> bool:
    path = _normalise(path)
    if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return True
    parts = path.split("/")
    return len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md"


def changed_contract_paths(paths: Iterable[str]) -> list[str]:
    return sorted({_normalise(path) for path in paths if is_protected(path)})


def metadata_gaps(paths: Iterable[str]) -> list[str]:
    changed = {_normalise(path) for path in paths}
    gaps: list[str] = []
    if changed & {"VERSION", "CHANGELOG.md"} and not {"VERSION", "CHANGELOG.md"} <= changed:
        gaps.extend(sorted({"VERSION", "CHANGELOG.md"} - changed))
    if changed_contract_paths(changed) and not {"VERSION", "CHANGELOG.md"} <= changed:
        gaps.extend(sorted({"VERSION", "CHANGELOG.md"} - changed))
    return sorted(set(gaps))


def _git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _event_base() -> str | None:
    explicit = os.environ.get("GITHUB_BASE_SHA")
    if explicit:
        return explicit
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            event = {}
        pull_request = event.get("pull_request") or {}
        base = (pull_request.get("base") or {}).get("sha")
        if base:
            return base
        before = event.get("before")
        if before and set(before) != {"0"}:
            return before
    return None


def _resolve_revisions(base: str | None, head: str | None) -> tuple[str | None, str]:
    resolved_head = head or os.environ.get("GITHUB_SHA") or "HEAD"
    resolved_base = base or _event_base()
    if not resolved_base:
        try:
            resolved_base = _git("rev-parse", f"{resolved_head}^",)[0]
        except (subprocess.CalledProcessError, IndexError):
            resolved_base = None
    return resolved_base, resolved_head


def git_changed_paths(base: str | None, head: str, include_worktree: bool) -> list[str]:
    if base:
        paths = _git("diff", "--name-only", "--diff-filter=ACMRD", base, head)
    else:
        paths = _git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", head)
    if include_worktree:
        paths.extend(_git("diff", "--name-only", "--diff-filter=ACMRD"))
        paths.extend(_git("diff", "--cached", "--name-only", "--diff-filter=ACMRD"))
    return sorted({_normalise(path) for path in paths})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base Git revision")
    parser.add_argument("--head", help="head Git revision")
    parser.add_argument("--include-worktree", action="store_true")
    args = parser.parse_args(argv)
    try:
        base, head = _resolve_revisions(args.base, args.head)
        changed = git_changed_paths(base, head, args.include_worktree)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    protected = changed_contract_paths(changed)
    gaps = metadata_gaps(changed)
    result = {
        "status": "valid" if not gaps else "invalid",
        "base": base,
        "head": head,
        "protected_changes": protected,
        "metadata_gaps": gaps,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
