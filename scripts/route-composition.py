#!/usr/bin/env python3
"""Select one primary governance skill and at most two optional collaborators."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "skill-capability-registry.json"
MAX_COLLABORATORS = 2
BOOLEAN_FIELDS = {
    "project_bootstrap",
    "governance",
    "ambiguous_goal",
    "acceptance_unclear",
    "failure",
    "inconsistency",
    "root_cause_unclear",
    "authorized_code_change",
    "test_failure",
    "windows_risk",
    "build",
    "install",
    "git",
    "process",
    "ui_automation",
    "long_running",
    "interrupted",
    "resume",
    "boundary",
    "dependency",
    "capacity",
    "rollback",
    "capability_mismatch",
    "continuous_development",
    "write",
    "external_side_effect",
    "consequential_claim",
    "explicit_deliberation",
    "explicit_pao",
}


def _registry() -> dict[str, dict[str, Any]]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["name"]: item for item in data["skills"]}


def _normalise_signals(request: dict[str, Any]) -> set[str]:
    signals = request.get("signals", [])
    if not isinstance(signals, list) or any(not isinstance(item, str) for item in signals):
        raise ValueError("signals must be an array of strings")
    result = {item.strip() for item in signals if item.strip()}
    for field in BOOLEAN_FIELDS:
        if field in request and not isinstance(request[field], bool):
            raise ValueError(f"{field} must be a boolean when provided")
    for field, signal in (
        ("project_bootstrap", "project_bootstrap"),
        ("governance", "governance"),
        ("ambiguous_goal", "ambiguous_goal"),
        ("acceptance_unclear", "acceptance_unclear"),
        ("failure", "failure"),
        ("inconsistency", "inconsistency"),
        ("root_cause_unclear", "root_cause_unclear"),
        ("authorized_code_change", "authorized_code_change"),
        ("test_failure", "test_failure"),
        ("windows_risk", "windows_risk"),
        ("build", "build"),
        ("install", "install"),
        ("git", "git"),
        ("process", "process"),
        ("ui_automation", "ui_automation"),
        ("long_running", "long_running"),
        ("interrupted", "interrupted"),
        ("resume", "resume"),
        ("boundary", "boundary"),
        ("dependency", "dependency"),
        ("capacity", "capacity"),
        ("rollback", "rollback"),
        ("capability_mismatch", "capability_mismatch"),
        ("continuous_development", "continuous_development"),
        ("write", "write"),
        ("external_side_effect", "external_side_effect"),
        ("consequential_claim", "consequential_claim"),
        ("explicit_deliberation", "explicit_deliberation"),
        ("explicit_pao", "explicit_pao"),
    ):
        if request.get(field) is True:
            result.add(signal)
    return result


def _choose_primary(request: dict[str, Any], signals: set[str], known: dict[str, dict[str, Any]]) -> tuple[str | None, list[str]]:
    explicit = request.get("explicit_skill")
    if explicit is not None and (not isinstance(explicit, str) or explicit not in known):
        raise ValueError("explicit_skill must be a known skill name or null")
    if explicit == "deliberate-project" or "explicit_deliberation" in signals:
        return "deliberate-project", ["explicit deliberation has highest priority"]
    if explicit == "project-agent-orchestrator" or "explicit_pao" in signals:
        return "project-agent-orchestrator", ["explicit PAO request selects PAO as primary"]
    if explicit:
        return explicit, ["explicit skill selection"]
    priorities = (
        ({"project_bootstrap", "governance"}, "bootstrap-codex-project", "project bootstrap or governance signal"),
        ({"ambiguous_goal", "acceptance_unclear"}, "intent-alignment", "goal or acceptance is unclear"),
        ({"failure", "inconsistency", "root_cause_unclear"}, "diagnose", "failure or root cause needs bounded diagnosis"),
        ({"authorized_code_change", "test_failure"}, "tdd-loop", "authorized code or test work is requested"),
        ({"windows_risk", "build", "install", "git", "process", "ui_automation"}, "execution-reliability", "execution environment has a reliability signal"),
        ({"long_running", "interrupted", "resume"}, "durable-context", "long-running or interrupted work needs continuity"),
        ({"boundary", "dependency", "capacity", "rollback"}, "architecture-health", "a structural boundary or capacity question is present"),
        ({"capability_mismatch"}, "capability-director", "the requested capability does not match the current tools"),
    )
    for matches, skill, reason in priorities:
        if signals & matches:
            return skill, [reason]
    return None, ["no primary routing signal was provided"]


def route(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("routing request must be an object")
    known = _registry()
    signals = _normalise_signals(request)
    primary, reasons = _choose_primary(request, signals, known)
    if primary is None:
        return {
            "status": "unknown",
            "primary_skill": None,
            "collaborators": [],
            "reasons": reasons,
            "degradation": "standalone",
            "budget": {"chars": 3000, "calls": 0, "depth": 0},
        }
    # A write, external side effect, or consequential completion claim always
    # passes through the Guard.  Keep the originally requested skill visible so
    # a caller can delegate after the gate instead of silently bypassing it.
    gated_primary = None
    guard_signals = {"write", "external_side_effect", "consequential_claim"}
    if signals & guard_signals and primary != "human-centered-reasoning-guard":
        gated_primary = primary
        primary = "human-centered-reasoning-guard"
        reasons.append("Guard is mandatory for write, external-side-effect, or consequential-claim signals")
    primary_record = known[primary]
    candidates = []
    for collaborator in primary_record["optional_collaborators"]:
        collaborator_signals = set(known[collaborator].get("route_signals", []))
        if signals & collaborator_signals:
            candidates.append(collaborator)
    collaborators = candidates[: min(MAX_COLLABORATORS, primary_record["max_collaborators"])]
    if candidates and not collaborators:
        reasons.append("matching helpers are not declared by the primary skill; use standalone fallback")
    result = {
        "status": "routed",
        "primary_skill": primary,
        "collaborators": collaborators,
        "reasons": reasons,
        "degradation": "composed" if collaborators else "standalone",
        "budget": {"chars": 3000, "calls": len(collaborators), "depth": 1 if collaborators else 0},
    }
    if gated_primary:
        result["gated_primary_skill"] = gated_primary
        result["gate"] = "human-centered-reasoning-guard"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="JSON routing request; '-' reads stdin")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
        result = route(json.loads(raw))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
