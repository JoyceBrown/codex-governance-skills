#!/usr/bin/env python3
"""Bounded, read-only execution preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


MAX_CHECKS = 8


def check(check_id: str, status: str, message: str) -> dict[str, str]:
    return {"id": check_id, "status": status, "message": message[:300]}


def git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded execution preflight")
    parser.add_argument("--root", default=os.getcwd(), help="project or action root")
    parser.add_argument(
        "--kind", choices=("ordinary", "build", "install", "publish", "delete", "replace", "ui", "process", "git"),
        default="ordinary",
    )
    parser.add_argument("--target", help="optional target path")
    parser.add_argument("--json", action="store_true", help="kept for explicit machine-readable use")
    args = parser.parse_args()

    raw_root = Path(args.root).expanduser()
    checks: list[dict[str, str]] = []
    blocked = False
    if not raw_root.is_absolute():
        checks.append(check("root.absolute", "FAIL", "root must be an absolute path"))
        blocked = args.kind in {"install", "publish", "delete", "replace", "process", "git"}
        root = raw_root.resolve()
    else:
        root = raw_root.resolve()
        checks.append(check("root.absolute", "PASS", "absolute root resolved"))

    if root.exists() and root.is_dir():
        checks.append(check("root.exists", "PASS", "root directory exists"))
    else:
        checks.append(check("root.exists", "FAIL", "root directory does not exist"))
        blocked = True

    path_text = str(root)
    if len(path_text) >= 240:
        checks.append(check("path.length", "WARN", f"resolved path length is {len(path_text)}"))
        blocked = blocked or args.kind in {"build", "install", "publish", "delete", "replace"}
    elif any(ord(char) > 127 for char in path_text):
        checks.append(check("path.encoding", "WARN", "path contains non-ASCII characters; verify tool support"))
    else:
        checks.append(check("path.encoding", "PASS", "path is ASCII"))

    target = Path(args.target).expanduser().resolve() if args.target else None
    if target:
        target_ok = target.exists()
        checks.append(check("target.exists", "PASS" if target_ok else "WARN", "target exists" if target_ok else "target is not present yet"))
        if args.kind in {"install", "publish", "delete", "replace"} and not target_ok:
            blocked = True

    git_root = git_value(root, "rev-parse", "--show-toplevel")
    if git_root:
        head = git_value(root, "rev-parse", "--short", "HEAD") or "unknown"
        branch = git_value(root, "branch", "--show-current") or "detached"
        checks.append(check("git.identity", "PASS", f"repository={Path(git_root).name}; branch={branch}; head={head}"))
    elif args.kind == "git":
        checks.append(check("git.identity", "FAIL", "root is not a readable Git worktree"))
        blocked = True
    else:
        checks.append(check("git.identity", "INFO", "no Git identity required or available"))

    status = "BLOCKED" if blocked else ("WARN" if any(item["status"] == "WARN" for item in checks) else "READY")
    root_fingerprint = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    result = {
        "schema": "execution-reliability-preflight-v1",
        "status": status,
        "risk": "high" if args.kind in {"install", "publish", "delete", "replace", "process", "git"} else "low",
        "scope": args.kind,
        "root": root.name or "root",
        "root_fingerprint": root_fingerprint,
        "checks": checks[:MAX_CHECKS],
        "next_action": "inspect failed checks before proceeding" if status == "BLOCKED" else "continue with target-specific verification",
        "budget": {"checks": min(len(checks), MAX_CHECKS), "chars": 2400},
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 2 if status == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
