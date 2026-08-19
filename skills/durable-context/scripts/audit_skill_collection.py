#!/usr/bin/env python3
"""Read-only audit for a Codex skill source/install collection.

The auditor reports metadata, path hygiene, runtime targets, Git state, and
normalised source/install manifests. It never writes to the inspected trees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA = "skill-collection-audit-v1"
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    "node_modules",
    "_backup",
}
EXCLUDED_FILES = {".env", "runtime.conf"}
TEXT_SUFFIXES = {
    ".conf",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]:[\\/][^<>\r\n\"']+)")
ABSOLUTE_FILE_RE = re.compile(
    r"(?i)([A-Za-z]:[\\/][^<>\r\n\"']+?\.(?:py|ps1|js|sh|cmd|bat|exe))"
)
PLACEHOLDER_FILE_RE = re.compile(
    r"(?i)<skill[_-]dir>[\\/]([^<>\r\n\"']+?\.(?:py|ps1|js|sh|cmd|bat|exe))"
)
RELATIVE_FILE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_:/\\])((?:scripts|bin|src)[\\/][^<>\r\n\"']+?\.(?:py|ps1|js|sh|cmd|bat|exe))"
)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", re.DOTALL)
NAME_RE = re.compile(
    r"(?mi)^\s*name\s*:\s*(?:\"([^\"]+)\"|'([^']+)'|([^#\r\n]+?))\s*(?:#.*)?$"
)


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _issue(
    issues: list[dict[str, Any]],
    code: str,
    severity: str,
    path: str | Path,
    message: str,
    **extra: Any,
) -> None:
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "path": str(path),
        "message": message,
    }
    item.update(extra)
    issues.append(item)


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return any(part in EXCLUDED_DIRS for part in parts)


def _skill_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    candidates: set[Path] = set()
    if (root / "SKILL.md").is_file():
        candidates.add(root)
    for skill_md in root.rglob("SKILL.md"):
        if skill_md.is_file() and not _is_excluded(skill_md, root):
            candidates.add(skill_md.parent)
    return sorted(candidates, key=lambda item: str(item).lower())


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _frontmatter_name(skill_md: Path) -> Optional[str]:
    content = _read_text(skill_md)
    if content is None:
        return None
    match = FRONTMATTER_RE.search(content)
    if not match:
        return None
    name_match = NAME_RE.search(match.group(1))
    if not name_match:
        return None
    return next((part.strip() for part in name_match.groups() if part), None)


def _run_validator(skill_dir: Path, validator: Optional[Path]) -> dict[str, Any]:
    if validator is None:
        return {"status": "unavailable", "message": "quick_validate.py was not found"}
    if not validator.is_file():
        return {"status": "unavailable", "message": "quick_validate.py does not exist"}
    try:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(validator), str(skill_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "error", "message": str(exc)}
    output = (completed.stdout or completed.stderr).strip()
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "message": output[-1000:],
    }


def _normalised_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    # Normalise line endings for UTF-8 text, including extensionless files such
    # as .gitignore and LICENSE. Binary assets retain their original bytes.
    if b"\x00" not in data:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def _manifest(root: Path) -> tuple[str, int, list[str], dict[str, str]]:
    entries: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or _is_excluded(path, root) or path.name in EXCLUDED_FILES:
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(_normalised_bytes(path)).hexdigest()
        entries.append((relative, digest))
    entries.sort()
    payload = "".join(f"{relative}\0{digest}\n" for relative, digest in entries).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), len(entries), [relative for relative, _ in entries], dict(entries)


def _git_info(skill_dir: Path) -> Optional[dict[str, Any]]:
    if not (skill_dir / ".git").exists():
        return None

    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(skill_dir), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return (result.stdout or "").strip()

    try:
        return {
            "path": str(skill_dir),
            "head": run("rev-parse", "HEAD") or None,
            "branch": run("branch", "--show-current") or None,
            "dirty": bool(run("status", "--porcelain")),
            "remotes": run("remote", "-v").splitlines(),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"path": str(skill_dir), "error": str(exc)}


def _scope_for_file(path: Path, skill_dir: Path) -> str:
    relative = path.relative_to(skill_dir).as_posix().lower()
    name = path.name.lower()
    if name == "runtime.conf":
        return "runtime"
    if "history" in name or "/docs/" in f"/{relative}" or relative.startswith("docs/"):
        return "historical"
    if relative.startswith("examples/") or name.startswith("readme"):
        return "documentation"
    if name in {"skill.md", "agents.md"} or relative.startswith("references/"):
        return "documentation"
    if path.suffix.lower() in TEXT_SUFFIXES:
        return "implementation"
    return "other"


def _path_findings(
    skill_dir: Path, issues: list[dict[str, Any]], root_kind: str, install_root: Path
) -> None:
    for path in skill_dir.rglob("*"):
        if (
            not path.is_file()
            or _is_excluded(path, skill_dir)
            or path.name in {".env", "runtime.conf"}
            or path.suffix.lower() not in TEXT_SUFFIXES
        ):
            continue
        content = _read_text(path)
        if not content or "\x00" in content:
            continue
        scope = _scope_for_file(path, skill_dir)
        for match in ABSOLUTE_PATH_RE.finditer(content):
            value = match.group(1).rstrip("`'\",.;)")
            drive = value[:1].upper()
            if drive not in {"C", "E"}:
                continue
            if drive == "C":
                if scope == "historical":
                    code, severity = "STALE_HISTORICAL_PATH", "warning"
                elif scope == "documentation":
                    code, severity = "STALE_DOCUMENTATION_PATH", "warning"
                elif scope == "runtime":
                    code, severity = "STALE_RUNTIME_PATH", "fail"
                else:
                    code, severity = "STALE_SKILL_PATH", "warning"
                _issue(
                    issues,
                    code,
                    severity,
                    path,
                    f"C: drive absolute path found in {scope} content",
                    scope=root_kind,
                    content_scope=scope,
                )
            elif scope in {"documentation", "implementation"}:
                _issue(
                    issues,
                    "ABSOLUTE_SKILL_PATH",
                    "warning",
                    path,
                    f"E: drive absolute path found in {scope} content",
                    scope=root_kind,
                    content_scope=scope,
                )
            elif scope == "runtime":
                try:
                    resolved = _path(value)
                    expected = install_root.resolve()
                    if not str(resolved).lower().startswith(str(expected).lower() + os.sep.lower()):
                        _issue(
                            issues,
                            "RUNTIME_PATH_OUTSIDE_INSTALL",
                            "warning",
                            path,
                            "runtime.conf points outside the active install root",
                            scope=root_kind,
                        )
                except OSError:
                    pass


def _runtime_targets(command: str, skill_dir: Path) -> list[Path]:
    targets: list[Path] = []
    for match in ABSOLUTE_FILE_RE.finditer(command):
        targets.append(_path(match.group(1)))
    for match in PLACEHOLDER_FILE_RE.finditer(command):
        raw = match.group(1).strip()
        targets.append((skill_dir / raw.replace("/", os.sep).replace("\\", os.sep)).resolve())
    for match in RELATIVE_FILE_RE.finditer(command):
        raw = match.group(1).strip()
        targets.append((skill_dir / raw.replace("/", os.sep).replace("\\", os.sep)).resolve())
    unique: list[Path] = []
    seen: set[str] = set()
    for target in targets:
        key = str(target).lower()
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


def _inspect_runtime(skill_dir: Path, issues: list[dict[str, Any]], root_kind: str) -> Optional[dict[str, Any]]:
    config = skill_dir / "runtime.conf"
    if not config.is_file():
        return None
    content = _read_text(config) or ""
    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip().lower()] = value.strip()
    missing = [key for key in ("runtime", "command") if not values.get(key)]
    if missing:
        _issue(
            issues,
            "RUNTIME_CONF_INVALID",
            "fail",
            config,
            f"runtime.conf is missing: {', '.join(missing)}",
            scope=root_kind,
        )
    command = values.get("command", "")
    if re.search(r"(?i)(?<![A-Za-z0-9])C:[\\/]", command):
        _issue(
            issues,
            "STALE_RUNTIME_PATH",
            "fail",
            config,
            "runtime.conf command contains a C: drive path",
            scope=root_kind,
        )
    targets = _runtime_targets(command, skill_dir)
    for target in targets:
        if not target.is_file():
            _issue(
                issues,
                "RUNTIME_TARGET_MISSING",
                "fail",
                config,
                f"runtime command target does not exist: {target.name}",
                scope=root_kind,
            )
    if command and not targets:
        _issue(
            issues,
            "RUNTIME_TARGET_UNCHECKED",
            "warning",
            config,
            "runtime command contains no recognised script target",
            scope=root_kind,
        )
    return {"path": str(config), "runtime": values.get("runtime"), "command": command, "targets": [str(t) for t in targets]}


def _scan_root(
    root: Path,
    root_kind: str,
    validator: Optional[Path],
    issues: list[dict[str, Any]],
    install_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not root.is_dir():
        _issue(issues, f"{root_kind.upper()}_ROOT_MISSING", "fail", root, "skill root does not exist")
        return [], []
    skills: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []
    for skill_dir in _skill_dirs(root):
        skill_md = skill_dir / "SKILL.md"
        name = _frontmatter_name(skill_md)
        validation = _run_validator(skill_dir, validator)
        record: dict[str, Any] = {
            "root": root_kind,
            "path": str(skill_dir),
            "directory_name": skill_dir.name,
            "name": name,
            "validation": validation,
        }
        skills.append(record)
        if validation["status"] == "fail":
            _issue(issues, "SKILL_INVALID", "fail", skill_md, validation.get("message", "skill validation failed"), scope=root_kind)
        elif validation["status"] in {"unavailable", "error"}:
            _issue(issues, "VALIDATOR_UNAVAILABLE", "warning", skill_md, validation.get("message", "validator unavailable"), scope=root_kind)
        if not name:
            _issue(issues, "FRONTMATTER_NAME_MISSING", "fail", skill_md, "could not read frontmatter name", scope=root_kind)
        elif name != skill_dir.name:
            _issue(issues, "FRONTMATTER_NAME_MISMATCH", "fail", skill_md, f"frontmatter name '{name}' does not match directory '{skill_dir.name}'", scope=root_kind)
        runtime = _inspect_runtime(skill_dir, issues, root_kind)
        if runtime:
            runtimes.append(runtime)
        _path_findings(skill_dir, issues, root_kind, install_root)
        git = _git_info(skill_dir)
        if git:
            record["git"] = git
    names: dict[str, list[str]] = {}
    for skill in skills:
        if skill["name"]:
            names.setdefault(skill["name"], []).append(skill["path"])
    for name, paths in names.items():
        if len(paths) > 1:
            _issue(issues, "DUPLICATE_SKILL_NAME", "fail", root, f"skill name '{name}' appears {len(paths)} times", scope=root_kind, matches=paths)
    return skills, runtimes


def _inspect_hooks(path: Optional[Path], issues: list[dict[str, Any]], install_root: Path) -> Optional[dict[str, Any]]:
    if path is None:
        return None
    if not path.is_file():
        _issue(issues, "HOOK_CONFIG_MISSING", "warning", path, "active hooks.json was not found")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _issue(issues, "HOOK_CONFIG_INVALID", "fail", path, f"cannot parse hooks.json: {exc}")
        return None
    strings: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    for value in strings:
        for match in ABSOLUTE_PATH_RE.finditer(value):
            found = match.group(1).rstrip("`'\",.;)")
            if found[:1].upper() == "C":
                _issue(issues, "STALE_ACTIVE_PATH", "fail", path, "active hooks configuration contains a C: drive path", scope="active_config")
            elif found[:1].upper() == "E":
                try:
                    expected = install_root.resolve()
                    if not str(_path(found)).lower().startswith(str(expected).lower() + os.sep.lower()):
                        _issue(issues, "ACTIVE_PATH_OUTSIDE_INSTALL", "warning", path, "active hooks configuration points outside the install root", scope="active_config")
                except OSError:
                    pass
        for match in ABSOLUTE_FILE_RE.finditer(value):
            target = _path(match.group(1))
            if not target.is_file():
                _issue(issues, "HOOK_TARGET_MISSING", "fail", path, f"active hook target does not exist: {target.name}", scope="active_config")
    return {"path": str(path), "string_count": len(strings)}


def _hash_compare(
    source_skills: Iterable[dict[str, Any]],
    install_skills: Iterable[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_by_name = {skill["name"]: skill for skill in source_skills if skill.get("name")}
    install_by_name = {skill["name"]: skill for skill in install_skills if skill.get("name")}
    comparisons: list[dict[str, Any]] = []
    for name in sorted(set(source_by_name) | set(install_by_name)):
        source = source_by_name.get(name)
        install = install_by_name.get(name)
        if not source:
            if ".system" in Path(install["path"]).parts:
                continue
            _issue(issues, "INSTALL_WITHOUT_SOURCE", "warning", install["path"], f"installed skill '{name}' has no matching source skill")
            comparisons.append({"name": name, "source": None, "install": install["path"], "status": "install_only"})
            continue
        if not install:
            _issue(issues, "SOURCE_NOT_INSTALLED", "warning", source["path"], f"source skill '{name}' is not installed")
            comparisons.append({"name": name, "source": source["path"], "install": None, "status": "source_only"})
            continue
        source_hash, source_count, source_files, source_manifest = _manifest(_path(source["path"]))
        install_hash, install_count, install_files, install_manifest = _manifest(_path(install["path"]))
        same = source_hash == install_hash
        comparison = {
            "name": name,
            "source": source["path"],
            "install": install["path"],
            "source_hash": source_hash,
            "install_hash": install_hash,
            "source_file_count": source_count,
            "install_file_count": install_count,
            "status": "match" if same else "mismatch",
        }
        comparisons.append(comparison)
        if not same:
            only_source = sorted(set(source_files) - set(install_files))[:20]
            only_install = sorted(set(install_files) - set(source_files))[:20]
            changed = sorted(
                relative
                for relative in set(source_manifest) & set(install_manifest)
                if source_manifest[relative] != install_manifest[relative]
            )[:20]
            _issue(
                issues,
                "SOURCE_INSTALL_MISMATCH",
                "fail",
                source["path"],
                f"normalised source/install manifest differs for '{name}'",
                source_files_only=only_source,
                install_files_only=only_install,
                changed_files=changed,
            )
    return comparisons


def audit(
    *,
    install_root: str | Path,
    source_roots: Iterable[str | Path] = (),
    hooks_path: str | Path | None = None,
    validator_path: str | Path | None = None,
) -> dict[str, Any]:
    install = _path(install_root)
    sources = [_path(root) for root in source_roots]
    validator = _path(validator_path) if validator_path else None
    if validator is None:
        candidate = install / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
        validator = candidate if candidate.is_file() else None
    issues: list[dict[str, Any]] = []
    source_skills: list[dict[str, Any]] = []
    source_runtimes: list[dict[str, Any]] = []
    for root in sources:
        skills, runtimes = _scan_root(root, "source", validator, issues, install)
        source_skills.extend(skills)
        source_runtimes.extend(runtimes)
    install_skills, install_runtimes = _scan_root(install, "install", validator, issues, install)
    hook_target = _path(hooks_path) if hooks_path else install.parent / "hooks.json"
    hook_record = _inspect_hooks(hook_target, issues, install)
    comparisons = _hash_compare(source_skills, install_skills, issues)
    fail_count = sum(1 for item in issues if item["severity"] == "fail")
    warning_count = sum(1 for item in issues if item["severity"] == "warning")
    status = "fail" if fail_count else "warning" if warning_count else "pass"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "roots": {"source": [str(root) for root in sources], "install": str(install)},
        "skills": {"source": source_skills, "install": install_skills},
        "runtime": {"source": source_runtimes, "install": install_runtimes},
        "hooks": hook_record,
        "comparisons": comparisons,
        "issues": issues,
        "summary": {
            "source_skills": len(source_skills),
            "install_skills": len(install_skills),
            "failures": fail_count,
            "warnings": warning_count,
        },
    }


def _default_install_root() -> Path:
    home = os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    return _path(home) / "skills"


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Read-only audit of a Codex skill source/install collection")
    parser.add_argument("--install-root", default=str(_default_install_root()), help="active CODEX_HOME/skills directory")
    parser.add_argument("--source-root", action="append", default=[], help="source tree to scan; repeatable")
    parser.add_argument("--hooks", default=None, help="active hooks.json; pass explicitly to inspect it")
    parser.add_argument("--quick-validator", default=None, help="path to skill-creator quick_validate.py")
    parser.add_argument("--text", action="store_true", help="render a concise human-readable summary instead of JSON")
    args = parser.parse_args(argv)
    report = audit(
        install_root=args.install_root,
        source_roots=args.source_root,
        hooks_path=args.hooks,
        validator_path=args.quick_validator,
    )
    if args.text:
        print(f"status: {report['status']}")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        for issue in report["issues"]:
            print(f"[{issue['severity']}] {issue['code']}: {issue['path']} - {issue['message']}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
