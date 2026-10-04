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
    "outcome_status": {"OPEN", "PARTIAL", "ACCEPTED", "REJECTED", "UNKNOWN"},
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
    "outcome_status",
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
MAX_CHARS = 8000
MAX_CALLS = 8
GUARD_SKILL = "human-centered-reasoning-guard"
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
    required_budget = {"chars", "calls", "depth"}
    optional_budget = {"spent_chars", "spent_calls"}
    if not isinstance(budget, dict) or not required_budget.issubset(budget) or set(budget) - required_budget - optional_budget:
        raise CompositionValidationError("budget must contain chars, calls, depth, and only optional spent fields")
    for field, maximum in (("chars", MAX_CHARS), ("calls", MAX_CALLS), ("depth", MAX_DEPTH)):
        if not _is_int(budget[field]) or not 0 <= budget[field] <= maximum:
            raise CompositionValidationError(f"budget.{field} is outside its bounded integer range")
    for field, maximum in (("spent_chars", MAX_CHARS), ("spent_calls", MAX_CALLS)):
        if field in budget and (not _is_int(budget[field]) or not 0 <= budget[field] <= maximum):
            raise CompositionValidationError(f"budget.{field} is outside its bounded integer range")
    if budget.get("spent_chars", 0) > budget["chars"]:
        raise CompositionValidationError("budget.spent_chars cannot exceed budget.chars")
    if budget.get("spent_calls", 0) > budget["calls"]:
        raise CompositionValidationError("budget.spent_calls cannot exceed budget.calls")
    if known_skills is None:
        known_skills = _registry()
    for field in ("source_skill", "target_skill"):
        if envelope[field] not in known_skills:
            raise CompositionValidationError(f"unknown {field}: {envelope[field]}")
    source = known_skills[envelope["source_skill"]]
    target = known_skills[envelope["target_skill"]]
    if envelope["source_skill"] != envelope["target_skill"]:
        if envelope["target_skill"] not in source["optional_collaborators"]:
            raise CompositionValidationError(
                f"{envelope['source_skill']} is not allowed to call {envelope['target_skill']}"
            )
    if envelope["authority_owner"] != source["authority_owner"]:
        raise CompositionValidationError(
            "authority_owner must match the source skill's declared authority owner"
        )
    if envelope["side_effect"] not in target["allowed_side_effects"]:
        raise CompositionValidationError(
            f"{envelope['target_skill']} does not allow side_effect={envelope['side_effect']}"
        )
    if envelope["side_effect"] == "external_write" and envelope["source_skill"] != GUARD_SKILL and envelope["target_skill"] != GUARD_SKILL:
        raise CompositionValidationError("external_write requires the Guard as source or target")
    if "composition-v1" not in source.get("protocol_compatibility", []):
        raise CompositionValidationError(f"{envelope['source_skill']} does not support composition-v1")
    if "composition-v1" not in target.get("protocol_compatibility", []):
        raise CompositionValidationError(f"{envelope['target_skill']} does not support composition-v1")
    if envelope["degradation"] == "standalone" and envelope["source_skill"] != envelope["target_skill"]:
        raise CompositionValidationError("standalone envelopes must target the same skill")
    if envelope["degradation"] == "standalone" and envelope["parent_request_id"] is not None:
        raise CompositionValidationError("standalone envelopes cannot be child calls")
    if envelope["action_status"] == "BLOCKED" and envelope["execution_status"] == "COMPLETED":
        raise CompositionValidationError("a blocked action cannot be completed")
    if envelope["execution_status"] == "COMPLETED" and envelope["lifecycle"] != "completed":
        raise CompositionValidationError("COMPLETED execution_status requires completed lifecycle")
    if envelope["action_status"] == "BLOCKED" and envelope["lifecycle"] not in {"blocked", "partial", "abandoned"}:
        raise CompositionValidationError("blocked action requires blocked, partial, or abandoned lifecycle")
    if envelope["execution_status"] == "FAILED" and envelope["lifecycle"] == "completed":
        raise CompositionValidationError("FAILED execution_status cannot have completed lifecycle")
    if envelope["lifecycle"] == "completed" and envelope["execution_status"] != "COMPLETED":
        raise CompositionValidationError("completed lifecycle requires COMPLETED execution_status")
    if envelope["lifecycle"] == "completed" and envelope["degradation"] == "blocked":
        raise CompositionValidationError("blocked degradation cannot be completed")
    if envelope["degradation"] == "blocked" and envelope["lifecycle"] not in {"blocked", "abandoned"}:
        raise CompositionValidationError("blocked degradation requires blocked or abandoned lifecycle")
    if envelope["lifecycle"] == "blocked":
        if envelope["degradation"] != "blocked":
            raise CompositionValidationError("blocked lifecycle requires blocked degradation")
        if envelope["action_status"] != "BLOCKED" and envelope["recovery_status"] != "BLOCKED_UNCERTAINTY":
            raise CompositionValidationError("blocked lifecycle requires a blocking action or uncertainty")
    if envelope["lifecycle"] == "partial":
        if envelope["degradation"] != "partial":
            raise CompositionValidationError("partial lifecycle requires partial degradation")
        if envelope["execution_status"] == "COMPLETED":
            raise CompositionValidationError("partial lifecycle cannot claim completed execution")
    if envelope["recovery_status"] == "BLOCKED_UNCERTAINTY" and envelope["lifecycle"] not in {"blocked", "partial"}:
        raise CompositionValidationError("blocked uncertainty requires blocked or partial lifecycle")
    return envelope


def validate_lifecycle_transition(previous: str, current: str) -> None:
    """Reject lifecycle jumps that skip a required stopping or resume state."""
    if previous not in LIFECYCLE_TRANSITIONS or current not in LIFECYCLE_TRANSITIONS:
        raise CompositionValidationError("unknown lifecycle state")
    if current not in LIFECYCLE_TRANSITIONS[previous]:
        raise CompositionValidationError(f"invalid lifecycle transition: {previous} -> {current}")


def validate_lifecycle_history(history: list[str | dict[str, Any]]) -> list[str]:
    """Validate a finite lifecycle history without storing it as runtime state."""
    if not isinstance(history, list) or not history:
        raise CompositionValidationError("lifecycle history must be a non-empty array")
    states: list[str] = []
    for item in history:
        state = item.get("lifecycle") if isinstance(item, dict) else item
        if not isinstance(state, str) or state not in LIFECYCLE_TRANSITIONS:
            raise CompositionValidationError("lifecycle history contains an unknown state")
        states.append(state)
    if states[0] != "created":
        raise CompositionValidationError("lifecycle history must start at created")
    for previous, current in zip(states, states[1:]):
        validate_lifecycle_transition(previous, current)
    for index, state in enumerate(states[:-1]):
        if state in {"completed", "abandoned"}:
            raise CompositionValidationError("completed and abandoned are terminal lifecycle states")
    return states


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
    roots = [item for item in chain if item["parent_request_id"] is None]
    if len(roots) != 1:
        raise CompositionValidationError("a composition chain must contain exactly one root envelope")
    children: dict[str, list[dict[str, Any]]] = {item["request_id"]: [] for item in chain}
    for item in chain:
        parent = item["parent_request_id"]
        if parent is not None and parent not in by_id:
            raise CompositionValidationError(f"missing parent request_id: {parent}")
        if parent == item["request_id"]:
            raise CompositionValidationError("request cannot parent itself")
        if parent is not None:
            parent_item = by_id[parent]
            if item["source_skill"] != parent_item["target_skill"]:
                raise CompositionValidationError("child source_skill must equal its parent target_skill")
            children[parent].append(item)
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
    for item in chain:
        if len(children[item["request_id"]]) > known[item["target_skill"]]["max_collaborators"]:
            raise CompositionValidationError("target skill exceeded its max_collaborators limit")
    root = roots[0]
    spent_chars = 0
    spent_calls = 0
    guard_present = False
    allocation_by_parent: dict[str, dict[str, int]] = {}
    for item in chain:
        budget = item["budget"]
        if len(chain) > 1 and ("spent_chars" not in budget or "spent_calls" not in budget):
            raise CompositionValidationError("composed chains must report spent_chars and spent_calls")
        spent_chars += budget.get("spent_chars", 0)
        spent_calls += budget.get("spent_calls", 0)
        if item["source_skill"] == GUARD_SKILL or item["target_skill"] == GUARD_SKILL:
            guard_present = True
        parent_id = item["parent_request_id"]
        if parent_id is not None:
            parent_budget = by_id[parent_id]["budget"]
            allocation = allocation_by_parent.setdefault(parent_id, {"chars": 0, "calls": 0})
            allocation["chars"] += budget["chars"]
            allocation["calls"] += budget["calls"]
    for parent_id, allocation in allocation_by_parent.items():
        parent_budget = by_id[parent_id]["budget"]
        if allocation["chars"] > parent_budget["chars"] - parent_budget.get("spent_chars", 0):
            raise CompositionValidationError("child chars allocations exceed the parent's remaining budget")
        if allocation["calls"] > parent_budget["calls"] - parent_budget.get("spent_calls", 0):
            raise CompositionValidationError("child calls allocations exceed the parent's remaining budget")
    if spent_chars > root["budget"]["chars"] or spent_calls > root["budget"]["calls"]:
        raise CompositionValidationError("composition chain exceeded its root cumulative budget")
    for item in chain:
        if item["lifecycle"] == "completed":
            pending_descendants = [
                descendant
                for descendant in chain
                if descendant["request_id"] != item["request_id"]
                and item["request_id"] in _ancestor_ids(descendant, by_id)
                and descendant["lifecycle"] not in {"completed", "abandoned"}
            ]
            if pending_descendants:
                raise CompositionValidationError("completed requests cannot have active descendants")
    if any(item["side_effect"] == "external_write" for item in chain) and not guard_present:
        raise CompositionValidationError("external_write requires a Guard source or target in the chain")
    root_budget = root["budget"]
    if (spent_chars >= root_budget["chars"] or spent_calls >= root_budget["calls"]) and any(
        item["execution_status"] == "IN_PROGRESS" and item["lifecycle"] not in {"partial", "blocked", "abandoned", "completed"}
        for item in chain
    ):
        raise CompositionValidationError("an exhausted cumulative budget must stop or become partial")
    return chain


def _ancestor_ids(item: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> set[str]:
    ancestors: set[str] = set()
    parent_id = item["parent_request_id"]
    while parent_id is not None:
        ancestors.add(parent_id)
        parent_id = by_id[parent_id]["parent_request_id"]
    return ancestors


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
