#!/usr/bin/env python3
"""Validate and render a bounded execution receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


REQUIRED = ("request_id", "status", "risk", "scope", "target", "next_action")
ALLOWED = set(REQUIRED) | {"checks", "attempt", "retry", "review_candidate", "evidence_refs", "generated_at"}
SECRET = re.compile(r"(?i)(?:token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,;]+")


def clean(value: object) -> object:
    if isinstance(value, str):
        if ("\\" in value or "/" in value) and len(value) > 80:
            path = Path(value)
            return f"{path.name or 'path'}#{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"
        return SECRET.sub("[REDACTED]", value)[:600]
    if isinstance(value, list):
        return [clean(item) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key)[:80]: clean(item) for key, item in list(value.items())[:20]}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a bounded execution receipt")
    parser.add_argument("--input", help="JSON file; otherwise read stdin")
    parser.add_argument("--out", help="optional explicit receipt path")
    args = parser.parse_args()
    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": "execution-reliability-receipt-v1", "status": "BLOCKED", "error": str(error)[:200]}, ensure_ascii=False))
        return 2
    if not isinstance(value, dict) or any(not value.get(field) for field in REQUIRED):
        print(json.dumps({"schema": "execution-reliability-receipt-v1", "status": "BLOCKED", "error": "missing required receipt fields"}, ensure_ascii=False))
        return 2
    receipt = {key: clean(item) for key, item in value.items() if key in ALLOWED}
    receipt["schema"] = "execution-reliability-receipt-v1"
    receipt.setdefault("generated_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    rendered = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) > 2400:
        print(json.dumps({"schema": receipt["schema"], "status": "BLOCKED", "error": "receipt exceeds 2400 characters"}, ensure_ascii=False))
        return 2
    if args.out:
        destination = Path(args.out).expanduser()
        if any(part.lower() in {".agent-context", ".git"} for part in destination.parts):
            print(json.dumps({"schema": receipt["schema"], "status": "BLOCKED", "error": "receipt path is owned by another authority"}, ensure_ascii=False))
            return 2
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
