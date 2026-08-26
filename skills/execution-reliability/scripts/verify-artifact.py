#!/usr/bin/env python3
"""Verify an artifact's basic identity and optional metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a build artifact")
    parser.add_argument("--path", required=True)
    parser.add_argument("--name")
    parser.add_argument("--version")
    parser.add_argument("--metadata", help="JSON file containing metadata to compare")
    parser.add_argument("--sha256")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    checks: list[dict[str, str]] = []
    ok = path.is_file() and path.stat().st_size > 0 if path.exists() else False
    checks.append({"id": "artifact.nonempty", "status": "PASS" if ok else "FAIL", "message": "file exists and is non-empty" if ok else "artifact missing or empty"})
    if args.name:
        name_ok = path.name == args.name
        checks.append({"id": "artifact.name", "status": "PASS" if name_ok else "FAIL", "message": "name matches" if name_ok else "name mismatch"})
        ok = ok and name_ok
    metadata: dict[str, object] = {}
    if args.metadata:
        try:
            metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be an object")
            checks.append({"id": "artifact.metadata.read", "status": "PASS", "message": "metadata parsed"})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            checks.append({"id": "artifact.metadata.read", "status": "FAIL", "message": str(error)[:200]})
            ok = False
    if args.version:
        version_ok = str(metadata.get("version", "")) == args.version
        checks.append({"id": "artifact.version", "status": "PASS" if version_ok else "FAIL", "message": "version matches" if version_ok else "version missing or mismatch"})
        ok = ok and version_ok
    actual_digest = sha256(path) if ok and path.is_file() else None
    if args.sha256:
        digest_ok = actual_digest is not None and actual_digest.lower() == args.sha256.lower()
        checks.append({"id": "artifact.sha256", "status": "PASS" if digest_ok else "FAIL", "message": "digest matches" if digest_ok else "digest mismatch"})
        ok = ok and digest_ok
    result = {
        "schema": "execution-reliability-artifact-v1",
        "status": "READY" if ok else "BLOCKED",
        "artifact": path.name if all(ord(char) < 128 for char in path.name) else "redacted",
        "size": path.stat().st_size if path.exists() and path.is_file() else 0,
        "sha256": actual_digest,
        "checks": checks,
        "next_action": "artifact may enter the next authorized step" if ok else "stop and correct artifact identity",
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
