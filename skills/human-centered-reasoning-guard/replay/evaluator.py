#!/usr/bin/env python3
"""Bounded, zero-LLM replay over an authorized experience projection."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

MAX_NODES = 1000
MAX_DEPTH = 32
MAX_PATHS = 1000
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_VALUES = 100000
MAX_COUNTER = 10 ** 12
RESULTS = {"success", "partial", "failure", "unknown"}
PRIORITIES = {"goal_progress", "low_cost", "evidence_first", "balanced"}
NODE_FIELDS = {"node_id", "parent_id", "timestamp", "goal", "state_summary", "evidence_refs", "hypothesis_refs", "action", "result", "failure_class", "goal_progress", "constraints", "scope", "dependencies", "execution_cost", "risk", "status"}
COST_FIELDS = {"llm_calls", "input_tokens", "output_tokens", "elapsed_ms", "tool_calls"}
STRATEGY_FIELDS = {"branch_priority", "avoid_failure_classes", "max_depth", "early_stop_goal_progress", "cost_weight", "risk_weight", "require_same_scope"}
REQUEST_FIELDS = {"why", "what", "project_id", "environment_scope", "runtime_id", "dependencies", "constraints", "experience_nodes", "strategy"}


class ReplayInputError(ValueError):
    """Raised when replay input is incomplete, unsafe, or over budget."""


@dataclass(frozen=True)
class Candidate:
    node_id: str
    action: str
    result: str
    goal_progress: float
    evidence_count: int
    failure_class: str | None
    cost: float
    risk: float
    scope_match: bool


def _finite(value: Any, field: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise ReplayInputError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ReplayInputError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ReplayInputError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise ReplayInputError(f"{field} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ReplayInputError(f"{field} must be <= {maximum}")
    return number


def _object(value: Any, field: str, allowed: set[str], required: Iterable[str] = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayInputError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ReplayInputError(f"{field} keys must be strings")
    unknown = set(value) - allowed
    missing = set(required) - set(value)
    if unknown:
        raise ReplayInputError(f"{field} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ReplayInputError(f"{field} missing: {', '.join(sorted(missing))}")
    return value


def _string(value: Any, field: str, nullable: bool = False, maximum: int = 4096) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ReplayInputError(f"{field} must be a non-empty string" + (" or null" if nullable else ""))
    if len(value) > maximum:
        raise ReplayInputError(f"{field} exceeds {maximum} characters")
    return value


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReplayInputError(f"{field} must be a list of non-empty strings")
    if len(value) > 100 or any(len(item) > 256 for item in value):
        raise ReplayInputError(f"{field} exceeds 100 entries or 256 characters per entry")
    if len(set(value)) != len(value):
        raise ReplayInputError(f"{field} must not contain duplicate strings")
    return value


def _time(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value):
        raise ReplayInputError(f"{field} must be a timezone-qualified RFC3339 string or null")
    try:
        parsed = datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ReplayInputError(f"{field} must be a timezone-qualified RFC3339 string or null") from exc


def _sum(values: Iterable[float], field: str) -> float:
    try:
        return _finite(math.fsum(values), field, 0)
    except OverflowError as exc:
        raise ReplayInputError(f"{field} exceeds the finite numeric range") from exc


def _check_json_budget(value: Any) -> None:
    """Bound API payloads too; do not rely on the CLI file limit alone."""
    stack = [(value, 0)]
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if depth > MAX_JSON_DEPTH or visited > MAX_JSON_VALUES:
            raise ReplayInputError("Replay input exceeds JSON depth or value budget")
        if isinstance(item, dict):
            if len(item) + visited > MAX_JSON_VALUES:
                raise ReplayInputError("Replay input exceeds JSON value budget")
            if any(not isinstance(key, str) for key in item):
                raise ReplayInputError("JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(item) + visited > MAX_JSON_VALUES:
                raise ReplayInputError("Replay input exceeds JSON value budget")
            stack.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ReplayInputError("Replay input must contain only JSON values")
    total = 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(value):
            total += len(chunk.encode("utf-8"))
            if total > MAX_REQUEST_BYTES:
                raise ReplayInputError(f"Replay request exceeds {MAX_REQUEST_BYTES} bytes")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, ReplayInputError):
            raise
        raise ReplayInputError("Replay input must be bounded, finite JSON data") from exc


def _cost(node: dict[str, Any]) -> float:
    cost = _object(node.get("execution_cost", {}), "execution_cost", COST_FIELDS)
    for key, value in cost.items():
        if type(value) is not int:
            raise ReplayInputError(f"execution_cost.{key} must be a non-negative integer")
        _finite(value, f"execution_cost.{key}", 0, MAX_COUNTER)
    divisors = {"llm_calls": 1, "input_tokens": 10000, "output_tokens": 10000, "elapsed_ms": 100000, "tool_calls": 10}
    return _sum((cost.get(key, 0) / divisor for key, divisor in divisors.items()), "cost")


def _risk(node: dict[str, Any]) -> float:
    value = node.get("risk")
    if value is not None and (not isinstance(value, str) or value not in {"low", "medium", "high"}):
        raise ReplayInputError("risk must be low, medium, high, or null")
    return {None: 0.5, "low": 0.0, "medium": 0.5, "high": 1.0}[value]


def _strategy(strategy: dict[str, Any] | None) -> dict[str, Any]:
    if strategy is None:
        strategy = {}
    result = dict(_object(strategy, "strategy", STRATEGY_FIELDS))
    priority = result.get("branch_priority", "balanced")
    if not isinstance(priority, str) or priority not in PRIORITIES:
        raise ReplayInputError("branch_priority is invalid")
    depth = result.get("max_depth", 4)
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= MAX_DEPTH:
        raise ReplayInputError(f"max_depth must be an integer between 1 and {MAX_DEPTH}")
    for field, default in (("early_stop_goal_progress", 0.8), ("cost_weight", 0.1), ("risk_weight", 0.1)):
        result[field] = _finite(result.get(field, default), field, 0, 1)
    result["avoid_failure_classes"] = _strings(result.get("avoid_failure_classes", []), "avoid_failure_classes")
    if not isinstance(result.get("require_same_scope", False), bool):
        raise ReplayInputError("require_same_scope must be boolean")
    result["branch_priority"] = priority
    result["max_depth"] = depth
    return result


def _validate_node(node: Any, seen: set[str]) -> dict[str, Any]:
    required = ("node_id", "goal", "action", "result", "goal_progress", "scope", "status")
    _object(node, "experience node", NODE_FIELDS, required)
    node_id = _string(node["node_id"], "node_id", maximum=256)
    if node_id in seen:
        raise ReplayInputError("node_id must be unique and non-empty")
    seen.add(node_id)
    goal = _object(node["goal"], "goal", {"why", "what"}, ("why", "what"))
    _string(goal["why"], "goal.why")
    _string(goal["what"], "goal.what")
    _string(node["action"], "action")
    if not isinstance(node["result"], str) or node["result"] not in RESULTS:
        raise ReplayInputError("result is invalid")
    _finite(node["goal_progress"], "goal_progress", 0, 1)
    if not isinstance(node["status"], str) or node["status"] not in {"active", "superseded", "retired"}:
        raise ReplayInputError("status is invalid")
    scope = _object(node["scope"], "scope", {"project_id", "environment_scope", "runtime_id", "valid_until"}, ("project_id", "environment_scope"))
    _string(scope["project_id"], "scope.project_id", maximum=256)
    _string(scope["environment_scope"], "scope.environment_scope", maximum=256)
    _string(scope.get("runtime_id"), "scope.runtime_id", nullable=True, maximum=256)
    _time(scope.get("valid_until"), "scope.valid_until")
    _strings(node.get("constraints", []), "constraints")
    _strings(node.get("dependencies", []), "dependencies")
    _strings(node.get("evidence_refs", []), "evidence_refs")
    _strings(node.get("hypothesis_refs", []), "hypothesis_refs")
    _string(node.get("failure_class"), "failure_class", nullable=True, maximum=256)
    _time(node.get("timestamp"), "timestamp")
    if node.get("state_summary") is not None and not isinstance(node["state_summary"], dict):
        raise ReplayInputError("state_summary must be an object or null")
    _cost(node)
    _risk(node)
    parent = node.get("parent_id")
    _string(parent, "parent_id", nullable=True, maximum=256)
    if parent == node_id:
        raise ReplayInputError("parent_id must be another node_id or null")
    return node


def _validate_graph(nodes: list[dict[str, Any]]) -> None:
    by_id = {node["node_id"]: node for node in nodes}
    for node in nodes:
        if node.get("parent_id") is not None and node["parent_id"] not in by_id:
            raise ReplayInputError(f"node {node['node_id']} has a dangling parent_id")
    completed: set[str] = set()
    for node in nodes:
        chain: set[str] = set()
        current = node["node_id"]
        while current is not None and current not in completed:
            if current in chain:
                raise ReplayInputError("experience graph contains a cycle")
            chain.add(current)
            current = by_id[current].get("parent_id")
        completed.update(chain)


def _scope_match(node: dict[str, Any], project_id: str, environment_scope: str, runtime_id: str | None, dependencies: list[str] | None, now: datetime) -> bool:
    scope = node["scope"]
    if scope["project_id"] != project_id or scope["environment_scope"] != environment_scope:
        return False
    if scope.get("runtime_id") != runtime_id:
        return False
    if set(node.get("dependencies", [])) != set(dependencies or []):
        return False
    valid_until = _time(scope.get("valid_until"), "scope.valid_until")
    return valid_until is None or valid_until > now


def _utility(candidate: Candidate, strategy: dict[str, Any]) -> float:
    evidence = min(candidate.evidence_count / 3.0, 1.0)
    success = 1.0 if candidate.result == "success" else 0.5 if candidate.result == "partial" else 0.0
    cost_term = min(candidate.cost / 5.0, 1.0)
    priority = strategy["branch_priority"]
    if priority == "goal_progress":
        base = 0.65 * candidate.goal_progress + 0.20 * success + 0.15 * evidence
    elif priority == "low_cost":
        base = 0.55 * (1 - cost_term) + 0.30 * candidate.goal_progress + 0.15 * success
    elif priority == "evidence_first":
        base = 0.45 * evidence + 0.40 * candidate.goal_progress + 0.15 * success
    else:
        base = 0.45 * candidate.goal_progress + 0.20 * success + 0.20 * evidence + 0.15 * (1 - cost_term)
    return base - strategy["cost_weight"] * cost_term - strategy["risk_weight"] * candidate.risk


def _candidate(node: dict[str, Any]) -> Candidate:
    return Candidate(node["node_id"], node["action"], node["result"], _finite(node["goal_progress"], "goal_progress", 0, 1), len(node.get("evidence_refs", [])), node.get("failure_class"), _cost(node), _risk(node), True)


def _paths(nodes: list[dict[str, Any]], candidates: dict[str, Candidate], strategy: dict[str, Any]) -> list[dict[str, Any]]:
    children: dict[str | None, list[dict[str, Any]]] = {}
    for node in nodes:
        children.setdefault(node.get("parent_id"), []).append(node)
    stack = [(node, [], 0.0, 0.0) for node in reversed([node for node in nodes if node.get("parent_id") is None])]
    result: list[dict[str, Any]] = []
    while stack:
        node, path, cumulative, risk = stack.pop()
        node_id = node["node_id"]
        path2 = path + [node_id]
        item = candidates[node_id]
        cost = _sum((cumulative, item.cost), "path cost")
        risk = max(risk, item.risk)
        next_nodes = [child for child in children.get(node_id, []) if child["node_id"] in candidates]
        stopped = item.goal_progress >= strategy["early_stop_goal_progress"] and item.result == "success"
        truncated = bool(next_nodes) and len(path2) >= strategy["max_depth"] and not stopped
        if stopped or truncated or not next_nodes:
            if len(result) >= MAX_PATHS:
                raise ReplayInputError(f"Replay exceeds the {MAX_PATHS}-path budget")
            terminal = replace(item, cost=cost, risk=risk)
            result.append({"path": path2, "goal_progress": item.goal_progress, "cost_proxy": round(cost, 4), "utility": round(_utility(terminal, strategy), 4), "early_stopped": stopped, "depth_truncated": truncated})
        else:
            ranked = sorted(next_nodes, key=lambda child: _utility(candidates[child["node_id"]], strategy), reverse=True)
            stack.extend((child, path2, cost, risk) for child in reversed(ranked))
    return sorted(result, key=lambda item: (-item["utility"], item["path"]))


def evaluate(why: str, what: str, experience_nodes: Iterable[dict[str, Any]], strategy: dict[str, Any] | None = None, environment_scope: str | None = None, project_id: str | None = None, runtime_id: str | None = None, dependencies: list[str] | None = None, constraints: list[str] | None = None) -> dict[str, Any]:
    """Rank historical candidates, never execute actions or grant authorization.

    Project/environment identity is mandatory. Missing runtime/dependency
    context only matches history that declares no corresponding restriction.
    Parent chains must remain eligible; filtering never creates new roots.
    """
    for field, value in (("why", why), ("what", what)):
        _string(value, field)
    _string(project_id, "project_id", maximum=256)
    _string(environment_scope, "environment_scope", maximum=256)
    _string(runtime_id, "runtime_id", nullable=True, maximum=256)
    deps = None if dependencies is None else _strings(dependencies, "dependencies")
    required_constraints = [] if constraints is None else _strings(constraints, "constraints")
    policy = _strategy(strategy)
    if isinstance(experience_nodes, (str, bytes, dict)):
        raise ReplayInputError("experience_nodes must be an iterable of node objects")
    try:
        raw = list(islice(experience_nodes, MAX_NODES + 1))
    except TypeError as exc:
        raise ReplayInputError("experience_nodes must be an iterable of node objects") from exc
    if len(raw) > MAX_NODES:
        raise ReplayInputError(f"experience_nodes exceeds the {MAX_NODES}-node budget")
    _check_json_budget({"why": why, "what": what, "project_id": project_id, "environment_scope": environment_scope, "runtime_id": runtime_id, "dependencies": deps, "constraints": required_constraints, "strategy": policy, "experience_nodes": raw})
    seen: set[str] = set()
    nodes = [_validate_node(node, seen) for node in raw]
    _sum((_cost(node) for node in nodes), "total experience cost")
    _validate_graph(nodes)
    now = datetime.now(timezone.utc)
    eligible = {node["node_id"] for node in nodes if node["status"] == "active" and node.get("evidence_refs") and node["goal"]["why"] == why and node["goal"]["what"] == what and _scope_match(node, project_id, environment_scope, runtime_id, deps, now) and set(node.get("constraints", [])) == set(required_constraints) and node.get("failure_class") not in policy["avoid_failure_classes"]}
    children: dict[str | None, list[str]] = {}
    for node in nodes:
        children.setdefault(node.get("parent_id"), []).append(node["node_id"])
    reachable: set[str] = set()
    stack = list(children.get(None, []))
    while stack:
        node_id = stack.pop()
        if node_id in eligible:
            reachable.add(node_id)
            stack.extend(children.get(node_id, []))
    matching = [node for node in nodes if node["node_id"] in reachable]
    candidates = {node["node_id"]: _candidate(node) for node in matching}
    ranked = [{"node_id": item.node_id, "action": item.action, "result": item.result, "goal_progress": item.goal_progress, "evidence_count": item.evidence_count, "cost_proxy": round(item.cost, 4), "risk": item.risk, "scope_match": True, "utility": round(_utility(item, policy), 4)} for item in sorted(candidates.values(), key=lambda item: (-_utility(item, policy), item.node_id))]
    paths = _paths(matching, candidates, policy) if matching else []
    viable = [item for item in ranked if item["result"] in {"success", "partial"}]
    recommended = viable[0] if viable else None
    return {
        "replay_version": "cre-v1",
        "llm_calls": 0,
        "candidates": ranked,
        "paths": paths,
        "recommended": recommended,
        "status": "CANDIDATES_FOUND" if ranked else "NO_APPLICABLE_EXPERIENCE",
        "next_action": "VERIFY_CANDIDATE" if recommended is not None else "REASON_OR_COLLECT_EVIDENCE",
        "recommendation_kind": "historical_candidate",
        "execution_authorized": False,
        "current_truth_established": False,
        "historical_boundary": "Replay only evaluates active, evidenced experiences under the exact project, environment, runtime, dependency, validity, and constraint scope supplied by the host. It cannot create an unvisited result or establish current truth.",
    }


def _reject_constant(value: str) -> Any:
    raise ReplayInputError(f"JSON constant {value} is not allowed")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayInputError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded zero-LLM HCR Cognitive Replay evaluator")
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        with args.request.open("rb") as source:
            data = source.read(MAX_REQUEST_BYTES + 1)
        if len(data) > MAX_REQUEST_BYTES:
            raise ReplayInputError(f"Replay request exceeds {MAX_REQUEST_BYTES} bytes")
        request = json.loads(data.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        _object(request, "request", REQUEST_FIELDS, ("why", "what", "project_id", "environment_scope", "constraints", "experience_nodes"))
        if not isinstance(request["experience_nodes"], list):
            raise ReplayInputError("experience_nodes must be an array")
        for field in ("constraints", "dependencies"):
            if field in request:
                _strings(request[field], field)
        if "strategy" in request:
            _object(request["strategy"], "strategy", STRATEGY_FIELDS)
        result = evaluate(**request)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise SystemExit(f"Replay input rejected: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
