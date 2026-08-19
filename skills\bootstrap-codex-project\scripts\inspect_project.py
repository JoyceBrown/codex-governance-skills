#!/usr/bin/env python3
"""Inspect a repository for facts needed by bootstrap-codex-project."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is expected.
    tomllib = None


EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
DEFAULT_MAX_FILES = 5000

LANGUAGE_EXTENSIONS = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".css": "CSS",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".go": "Go",
    ".html": "HTML",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".lua": "Lua",
    ".php": "PHP",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scss": "SCSS",
    ".sh": "Shell",
    ".sql": "SQL",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
}

MANIFESTS = {
    "package.json": "Node.js",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java/Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "pubspec.yaml": "Dart/Flutter",
}

LOCKFILES = {
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "uv.lock": "uv",
    "poetry.lock": "Poetry",
    "Pipfile.lock": "Pipenv",
    "Cargo.lock": "Cargo",
    "go.sum": "Go modules",
}

TEST_CONFIG_NAMES = {
    "jest.config.js", "jest.config.cjs", "jest.config.mjs", "jest.config.ts",
    "playwright.config.js", "playwright.config.ts", "pytest.ini", "tox.ini",
    "vitest.config.js", "vitest.config.mjs", "vitest.config.ts",
}

def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


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
    if "current" in tokens and tokens & {"current", "mainline", "work"}:
        return "current"
    return None


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def detect_git_root(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return str(Path(value).resolve()) if value else None


def scan_files(root: Path, max_files: int) -> tuple[list[Path], bool]:
    files: list[Path] = []
    truncated = False
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(names):
            files.append(Path(current) / name)
            if len(files) >= max_files:
                truncated = True
                return files, truncated
    return files, truncated


def extract_commands(root: Path, files: list[Path]) -> dict[str, Any]:
    commands: dict[str, Any] = {}

    package_files = [path for path in files if path.name == "package.json"]
    package_scripts: dict[str, dict[str, str]] = {}
    for path in package_files[:20]:
        data = read_json(path)
        scripts = data.get("scripts") if data else None
        if isinstance(scripts, dict):
            package_scripts[relative(path, root)] = {
                str(key): str(value) for key, value in scripts.items()
            }
    if package_scripts:
        commands["package_scripts"] = package_scripts

    pyproject = root / "pyproject.toml"
    if pyproject.exists() and tomllib is not None:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project_scripts = data.get("project", {}).get("scripts", {})
            if isinstance(project_scripts, dict) and project_scripts:
                commands["python_entry_points"] = project_scripts
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            commands["pyproject_parse_error"] = True

    makefile = next((root / name for name in ("Makefile", "makefile") if (root / name).exists()), None)
    if makefile:
        try:
            targets = []
            for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?![=])", line)
                if match and not match.group(1).startswith("."):
                    targets.append(match.group(1))
            if targets:
                commands["make_targets"] = sorted(set(targets))[:100]
        except OSError:
            pass

    return commands


def inspect(root: Path, max_files: int) -> dict[str, Any]:
    files, truncated = scan_files(root, max_files)
    rel_files = [relative(path, root) for path in files]
    rel_set = set(rel_files)

    language_counts = Counter(
        LANGUAGE_EXTENSIONS[path.suffix.lower()]
        for path in files
        if path.suffix.lower() in LANGUAGE_EXTENSIONS
    )

    manifests = [
        {"path": path, "ecosystem": MANIFESTS[Path(path).name]}
        for path in rel_files
        if Path(path).name in MANIFESTS
    ]
    present_names = {Path(path).name for path in rel_files}
    package_managers = sorted(
        {manager for filename, manager in LOCKFILES.items() if filename in present_names}
    )

    docs = sorted(
        path
        for path in rel_files
        if path.lower().endswith(".md")
        and (
            "/" not in path
            or path.lower().startswith("docs/")
            or "/docs/" in path.lower()
        )
    )
    planning_details = sorted(
        (
            {"path": path, "kind": kind}
            for path in rel_files
            if path.lower().endswith(".md")
            if (kind := planning_artifact_kind(path)) is not None
        ),
        key=lambda item: item["path"],
    )
    planning_files = [item["path"] for item in planning_details]
    agent_files = sorted(
        path
        for path in rel_files
        if Path(path).name in {"AGENTS.md", "AGENTS.override.md"}
    )
    skill_files = sorted(
        path for path in rel_files if path.startswith(".agents/skills/") and path.endswith("/SKILL.md")
    )
    codex_files = sorted(
        path for path in rel_files if path.startswith(".codex/")
    )
    ci_files = sorted(
        path
        for path in rel_files
        if path.startswith(".github/workflows/")
        or path in {".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"}
    )
    test_config_files = sorted(
        path
        for path in rel_files
        if Path(path).name in TEST_CONFIG_NAMES
        or Path(path).name.startswith(("jest.config.", "playwright.config.", "vitest.config."))
    )
    experience_signals = []
    if len(docs) >= 8:
        experience_signals.append("many-docs")
    if len(planning_files) > 1:
        experience_signals.append("competing-plans")
    if len(agent_files) > 1:
        experience_signals.append("nested-agent-rules")
    if len(package_managers) > 1:
        experience_signals.append("multiple-package-managers")
    if len(manifests) > 1:
        experience_signals.append("multiple-manifests")
    if codex_files:
        experience_signals.append("advanced-codex-surfaces")
    if skill_files:
        experience_signals.append("project-local-skills")
    if ci_files:
        experience_signals.append("ci-configured")

    top_level = sorted(path.name for path in root.iterdir()) if root.exists() else []

    return {
        "root": str(root),
        "non_empty": bool(top_level),
        "git_root": detect_git_root(root),
        "scan": {
            "file_count": len(files),
            "truncated": truncated,
            "complete": not truncated,
            "max_files": max_files,
            "required_follow_up": (
                "rerun with a higher --max-files value or targeted file reads"
                if truncated
                else None
            ),
        },
        "top_level": top_level[:200],
        "languages": [
            {"name": name, "file_count": count}
            for name, count in language_counts.most_common()
        ],
        "manifests": manifests[:100],
        "package_managers": package_managers,
        "commands": extract_commands(root, files),
        "experience_signals": experience_signals,
        "context_artifacts": {
            "readme": "README.md" if "README.md" in rel_set else None,
            "agents": agent_files,
            "docs": docs[:300],
            "planning": planning_files[:100],
            "planning_details": planning_details[:100],
            "codex": codex_files[:300],
            "skills": skill_files[:300],
            "ci": ci_files[:100],
            "test_configs": test_config_files[:100],
        },
        "write_risks": {
            "existing_readme": "README.md" in rel_set,
            "existing_root_agents": "AGENTS.md" in rel_set,
            "existing_project_codex_config": ".codex/config.toml" in rel_set,
            "multiple_planning_artifacts": len(planning_files) > 1,
            "requires_preservation_review": any(
                item in rel_set
                for item in ("README.md", "AGENTS.md", ".codex/config.toml")
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", help="Project root to inspect")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if args.max_files < 1:
        parser.error("--max-files must be positive")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(inspect(root, args.max_files), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
