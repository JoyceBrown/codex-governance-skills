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


def markdown_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in names:
            if not name.lower().endswith(".md"):
                continue
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if (
                rel in {"README.md", "PLANS.md"}
                or rel.startswith("docs/")
                or name in {"AGENTS.md", "AGENTS.override.md"}
            ):
                results.append(path)
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
            if claim is None:
                continue
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
    for path in files:
        rel = path.relative_to(root).as_posix()
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
    info.append({"code": "advanced-surfaces", "paths": advanced_surfaces})

    return {
        "root": str(root),
        "profile": profile,
        "ok": not errors,
        "summary": {
            "markdown_files": len(files),
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
