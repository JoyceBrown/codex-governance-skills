#!/usr/bin/env python3
"""Verify a target's identity without mutating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify target path and optional digest")
    parser.add_argument("--path", required=True)
    parser.add_argument("--type", choices=("any", "file", "dir"), default="any")
    parser.add_argument("--sha256")
    args = parser.parse_args()

    target = Path(args.path).expanduser().resolve()
    checks: list[dict[str, str]] = []
    ok = target.exists()
    checks.append({"id": "target.exists", "status": "PASS" if ok else "FAIL", "message": "target exists" if ok else "target does not exist"})
    if ok and args.type != "any":
        type_ok = target.is_file() if args.type == "file" else target.is_dir()
        checks.append({"id": "target.type", "status": "PASS" if type_ok else "FAIL", "message": f"expected {args.type}"})
        ok = ok and type_ok
    actual_digest = None
    if ok and args.sha256:
        if not target.is_file():
            checks.append({"id": "target.sha256", "status": "FAIL", "message": "sha256 requires a file"})
            ok = False
        else:
            actual_digest = digest(target)
            digest_ok = actual_digest.lower() == args.sha256.lower()
            checks.append({"id": "target.sha256", "status": "PASS" if digest_ok else "FAIL", "message": "digest matches" if digest_ok else "digest mismatch"})
            ok = ok and digest_ok
    result = {
        "schema": "execution-reliability-target-v1",
        "status": "READY" if ok else "BLOCKED",
        "target": target.name or "target",
        "target_fingerprint": hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:12],
        "target_type": "file" if target.is_file() else ("dir" if target.is_dir() else "missing"),
        "sha256": actual_digest,
        "checks": checks,
        "next_action": "use verified target" if ok else "inspect target identity before proceeding",
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
