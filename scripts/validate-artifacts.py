#!/usr/bin/env python3
"""Validate the small, shared artifact contract used by governance Skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class ArtifactValidationError(ValueError):
    pass


REQUIRED_COMMON = {"artifact_kind", "schema_version", "evidence_refs", "next_action", "budget"}
KIND_REQUIRED = {
    "receipt": {"status", "run_mode"},
    "alignment_card": {"goal", "visible_success", "scope", "unknowns", "intent_status"},
    "checkpoint": {"checkpoint_id", "task_id", "recovery_status"},
    "composition_envelope": {"request_id", "source_skill", "target_skill", "lifecycle"},
}


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactValidationError("artifact must be an object")
    missing = REQUIRED_COMMON - value.keys()
    if missing:
        raise ArtifactValidationError(f"missing common fields: {sorted(missing)}")
    kind = value["artifact_kind"]
    if kind not in KIND_REQUIRED:
        raise ArtifactValidationError(f"unknown artifact_kind: {kind!r}")
    missing = KIND_REQUIRED[kind] - value.keys()
    if missing:
        raise ArtifactValidationError(f"missing {kind} fields: {sorted(missing)}")
    if value["schema_version"] not in {"artifact-v1", "composition-v1"}:
        raise ArtifactValidationError("unsupported schema_version")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 20 or any(not isinstance(item, str) or not item.strip() for item in refs):
        raise ArtifactValidationError("evidence_refs must be a bounded string array")
    if value["next_action"] is not None and (not isinstance(value["next_action"], str) or len(value["next_action"]) > 1000):
        raise ArtifactValidationError("next_action must be null or a bounded string")
    budget = value["budget"]
    if not isinstance(budget, dict) or set(budget) - {"chars", "calls", "depth", "spent_chars", "spent_calls"}:
        raise ArtifactValidationError("budget has unsupported fields")
    for key in ("chars", "calls", "depth"):
        if not isinstance(budget.get(key), int) or isinstance(budget[key], bool) or budget[key] < 0:
            raise ArtifactValidationError(f"budget.{key} must be a non-negative integer")
    for key in ("spent_chars", "spent_calls"):
        if key in budget and (not isinstance(budget[key], int) or budget[key] < 0 or budget[key] > budget[key.replace("spent_", "")]):
            raise ArtifactValidationError(f"budget.{key} exceeds its allowance")
    for field in ("status", "recovery_status", "intent_status", "action_status", "review_status", "execution_status"):
        if field in value and (not isinstance(value[field], str) or not value[field].strip() or len(value[field]) > 64):
            raise ArtifactValidationError(f"{field} must be a bounded non-empty string")
    if kind == "receipt" and value["run_mode"] not in {"standalone", "composed", "pao", "pao_develop", "non_pao"}:
        raise ArtifactValidationError("receipt.run_mode is not a supported mode")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="JSON artifact or array; '-' reads stdin")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
        value = json.loads(raw)
        items = value if isinstance(value, list) else [value]
        for item in items:
            validate_artifact(item)
    except (OSError, json.JSONDecodeError, ArtifactValidationError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "valid", "count": len(items)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
