#!/usr/bin/env python3
"""Validate the small, bounded composition-v1 protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "composition.schema.json"
REGISTRY_PATH = ROOT / "docs" / "skill-capability-registry.json"

STATUS_ENUMS = {
    "claim_kind": {"observed", "inferred", "proposed", "verified"},
    "intent_status": {"DECIDED", "ASSUMED", "OPEN", "CONFLICTED"},
    "recovery_status": {"FOUND", "PARTIAL", "NOT_FOUND", "CONFLICTED", "BLOCKED_UNCERTAINTY"},
    "action_status": {"READY", "WARN", "BLOCKED", "PARTIAL"},
    "review_status": {"PASS", "ISSUE", "ABSTAIN", "OPEN"},
    "execution_status": {"IN_PROGRESS", "COMPLETED", "FAILED", "UNKNOWN"},
    "side_effect": {"none", "project_write", "external_write"},
    "degradation": {"standalone", "composed", "partial", "blocked"},
    "lifecycle": {"created", "routed", "running", "waiting", "partial", "blocked", "resumed", "completed", "abandoned"},
}
REQUIRED = {
    "schema_version",
    "request_id",
    "parent_request_id",
    "source_skill",
    "target_skill",
    "scope",
    "claim_kind",
    "intent_status",
    "recovery_status",
    "action_status",
    "review_status",
    "execution_status",
    "authority_owner",
    "side_effect",
    "evidence_refs",
    "next_action",
    "degradation",
    "budget",
    "lifecycle",
}
ALLOWED_KEYS = REQUIRED
MAX_DEPTH = 2
LIFECYCLE_TRANSITIONS = {
    "created": {"routed", "abandoned"},
    "routed": {"running", "waiting", "blocked", "abandoned"},
    "running": {"waiting", "partial", "blocked", "completed", "abandoned"},
    "waiting": {"resumed", "blocked", "abandoned"},
    "resumed": {"running", "waiting", "partial", "blocked", "completed", "abandoned"},
    "partial": {"running", "completed", "blocked", "abandoned"},
    "blocked": {"resumed", "abandoned"},
    "completed": set(),
    "abandoned": set(),
}


class CompositionValidationError(ValueError):
    """Raised when a composition envelope or chain violates composition-v1."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _registry() -> dict[str, dict[str, Any]]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["name"]: item for item in data["skills"]}


def validate_envelope(envelope: dict[str, Any], *, known_skills: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return the envelope when it satisfies the bounded protocol."""
    if not isinstance(envelope, dict):
        raise CompositionValidationError("envelope must be an object")
    missing = REQUIRED - envelope.keys()
    unknown = set(envelope) - ALLOWED_KEYS
    if missing:
        raise CompositionValidationError(f"missing required fields: {sorted(missing)}")
    if unknown:
        raise CompositionValidationError(f"unknown fields are not allowed: {sorted(unknown)}")
    if envelope["schema_version"] != "composition-v1":
        raise CompositionValidationError("schema_version must be composition-v1")
    for field in ("request_id", "source_skill", "target_skill", "scope", "authority_owner"):
        value = envelope[field]
        if not isinstance(value, str) or not value.strip():
            raise CompositionValidationError(f"{field} must be a non-empty string")
    if len(envelope["request_id"]) > 128 or len(envelope["scope"]) > 2000:
        raise CompositionValidationError("request_id or scope exceeds its limit")
    parent = envelope["parent_request_id"]
    if parent is not None and (not isinstance(parent, str) or not parent.strip() or len(parent) > 128):
        raise CompositionValidationError("parent_request_id must be null or a bounded string")
    for field, values in STATUS_ENUMS.items():
        if envelope[field] not in values:
            raise CompositionValidationError(f"invalid {field}: {envelope[field]!r}")
    refs = envelope["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 20 or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in refs):
        raise CompositionValidationError("evidence_refs must contain at most 20 bounded strings")
    action = envelope["next_action"]
    if action is not None and (not isinstance(action, str) or len(action) > 1000):
        raise CompositionValidationError("next_action must be null or a bounded string")
    budget = envelope["budget"]
    if not isinstance(budget, dict) or set(budget) != {"chars", "calls", "depth"}:
        raise CompositionValidationError("budget must contain exactly chars, calls, and depth")
    for field, maximum in (("chars", 8000), ("calls", 8), ("depth", MAX_DEPTH)):
        if not _is_int(budget[field]) or not 0 <= budget[field] <= maximum:
            raise CompositionValidationError(f"budget.{field} is outside its bounded integer range")
    if envelope["degradation"] == "standalone" and envelope["source_skill"] != envelope["target_skill"]:
        raise CompositionValidationError("standalone envelopes must target the same skill")
    if envelope["action_status"] == "BLOCKED" and envelope["execution_status"] == "COMPLETED":
        raise CompositionValidationError("a blocked action cannot be completed")
    if envelope["lifecycle"] == "completed" and envelope["execution_status"] != "COMPLETED":
        raise CompositionValidationError("completed lifecycle requires COMPLETED execution_status")
    if known_skills is None:
        known_skills = _registry()
    for field in ("source_skill", "target_skill"):
        if envelope[field] not in known_skills:
            raise CompositionValidationError(f"unknown {field}: {envelope[field]}")
    owners = {item["authority_owner"] for item in known_skills.values()}
    if envelope["authority_owner"] not in owners:
        raise CompositionValidationError(f"unknown authority_owner: {envelope['authority_owner']}")
    return envelope


def validate_lifecycle_transition(previous: str, current: str) -> None:
    """Reject lifecycle jumps that skip a required stopping or resume state."""
    if previous not in LIFECYCLE_TRANSITIONS or current not in LIFECYCLE_TRANSITIONS:
        raise CompositionValidationError("unknown lifecycle state")
    if current not in LIFECYCLE_TRANSITIONS[previous]:
        raise CompositionValidationError(f"invalid lifecycle transition: {previous} -> {current}")


def validate_chain(chain: list[dict[str, Any]], *, max_depth: int = MAX_DEPTH) -> list[dict[str, Any]]:
    """Validate parent links, cycles, depth, and non-overridable guard blocks."""
    if not isinstance(chain, list) or not chain:
        raise CompositionValidationError("chain must be a non-empty array")
    if not _is_int(max_depth) or max_depth < 0 or max_depth > MAX_DEPTH:
        raise CompositionValidationError("max_depth is outside the protocol limit")
    known = _registry()
    by_id: dict[str, dict[str, Any]] = {}
    for item in chain:
        validate_envelope(item, known_skills=known)
        if item["request_id"] in by_id:
            raise CompositionValidationError(f"duplicate request_id: {item['request_id']}")
        by_id[item["request_id"]] = item
    for item in chain:
        parent = item["parent_request_id"]
        if parent is not None and parent not in by_id:
            raise CompositionValidationError(f"missing parent request_id: {parent}")
        if parent == item["request_id"]:
            raise CompositionValidationError("request cannot parent itself")
        depth = 0
        cursor = item
        seen: set[str] = set()
        while cursor["parent_request_id"] is not None:
            request_id = cursor["request_id"]
            if request_id in seen:
                raise CompositionValidationError("composition chain contains a cycle")
            seen.add(request_id)
            cursor = by_id[cursor["parent_request_id"]]
            depth += 1
            if depth > max_depth:
                raise CompositionValidationError("composition depth exceeds the bounded limit")
        if item["budget"]["depth"] < depth:
            raise CompositionValidationError("envelope depth budget is smaller than its parent path")
        ancestor_id = item["parent_request_id"]
        while ancestor_id is not None:
            ancestor = by_id[ancestor_id]
            if ancestor["authority_owner"] == "authorization_and_completion_gate" and ancestor["action_status"] == "BLOCKED":
                if item["action_status"] in {"READY", "WARN"} or item["execution_status"] == "COMPLETED":
                    raise CompositionValidationError("a descendant cannot override a Guard BLOCKED action")
            ancestor_id = ancestor["parent_request_id"]
    return chain


def _load_input(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="JSON envelope or chain; '-' reads stdin")
    args = parser.parse_args(argv)
    try:
        value = _load_input(args.path)
        if isinstance(value, list):
            validate_chain(value)
            result = {"status": "valid", "kind": "chain", "count": len(value)}
        else:
            validate_envelope(value)
            result = {"status": "valid", "kind": "envelope", "request_id": value["request_id"]}
    except (OSError, json.JSONDecodeError, CompositionValidationError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
