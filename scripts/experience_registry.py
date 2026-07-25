#!/usr/bin/env python3
"""Manage a private, reviewable learning registry for bootstrap-codex-project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCOPES = {"project_specific", "project_family", "cross_project"}
STATUSES = {"candidate", "accepted_local", "promoted", "rejected", "retired"}
CAPTURE_MODES = {"off", "ask", "auto_sanitized"}
SEVERITIES = {"low", "medium", "high", "critical"}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bas_sk_[A-Za-z0-9_-]{16,}\b"),
)
PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_store() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "learning" / "bootstrap-codex-project"


def sanitize(value: str, limit: int = 1200) -> str:
    text = value.strip()
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    text = PERSONAL_PATH_RE.sub("<user-home>", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def normalize_values(values: list[str] | None) -> list[str]:
    return sorted({sanitize(value, 120).lower() for value in values or [] if value.strip()})


def project_fingerprint(project_root: str | Path | None) -> str | None:
    if not project_root:
        return None
    normalized = str(Path(project_root).expanduser().resolve()).replace("\\", "/").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def candidate_fingerprint(
    problem: str,
    preferred_response: str,
    scope: str,
    project_types: list[str],
) -> str:
    payload = "\n".join(
        (
            sanitize(problem).lower(),
            sanitize(preferred_response).lower(),
            scope,
            ",".join(project_types),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_records(store: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    candidates = store / "candidates"
    if not candidates.exists():
        return records
    for path in sorted(candidates.glob("EXP-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def write_record(store: Path, record: dict[str, Any]) -> Path:
    candidates = store / "candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    path = candidates / f"{record['pattern_id']}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def capture(
    store: Path,
    *,
    problem: str,
    observed_failure: str,
    preferred_response: str,
    scope: str,
    project_root: str | Path | None = None,
    project_types: list[str] | None = None,
    signals: list[str] | None = None,
    evidence: list[str] | None = None,
    severity: str = "medium",
    reproduced: bool = False,
) -> tuple[dict[str, Any], bool]:
    if scope not in SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    if severity not in SEVERITIES:
        raise ValueError(f"invalid severity: {severity}")

    clean_problem = sanitize(problem)
    clean_preferred = sanitize(preferred_response)
    clean_types = normalize_values(project_types)
    fingerprint = candidate_fingerprint(
        clean_problem,
        clean_preferred,
        scope,
        clean_types,
    )
    project_id = project_fingerprint(project_root)
    now = utc_now()

    for record in load_records(store):
        if record.get("fingerprint") != fingerprint:
            continue
        record["last_seen_at"] = now
        record["occurrence_count"] = int(record.get("occurrence_count", 1)) + 1
        if project_id:
            projects = set(record.get("project_fingerprints", []))
            projects.add(project_id)
            record["project_fingerprints"] = sorted(projects)
        record["signals"] = sorted(
            set(record.get("signals", [])) | set(normalize_values(signals))
        )
        record["evidence_summaries"] = list(
            dict.fromkeys(
                list(record.get("evidence_summaries", []))
                + [sanitize(item, 400) for item in evidence or [] if item.strip()]
            )
        )[:20]
        record["reproduced"] = bool(record.get("reproduced")) or reproduced
        write_record(store, record)
        return record, False

    short_hash = fingerprint[:8]
    pattern_id = f"EXP-{datetime.now(timezone.utc):%Y%m%d}-{short_hash}"
    existing_ids = {item.get("pattern_id") for item in load_records(store)}
    suffix = 2
    base_id = pattern_id
    while pattern_id in existing_ids:
        pattern_id = f"{base_id}-{suffix}"
        suffix += 1

    record: dict[str, Any] = {
        "schema_version": 1,
        "pattern_id": pattern_id,
        "status": "candidate",
        "scope": scope,
        "severity": severity,
        "reproduced": reproduced,
        "problem": clean_problem,
        "observed_failure": sanitize(observed_failure),
        "preferred_response": clean_preferred,
        "project_types": clean_types,
        "signals": normalize_values(signals),
        "project_fingerprints": [project_id] if project_id else [],
        "evidence_summaries": [
            sanitize(item, 400) for item in evidence or [] if item.strip()
        ][:20],
        "occurrence_count": 1,
        "created_at": now,
        "last_seen_at": now,
        "fingerprint": fingerprint,
        "review": None,
        "promotion": None,
    }
    write_record(store, record)
    return record, True


def find_record(store: Path, pattern_id: str) -> dict[str, Any]:
    for record in load_records(store):
        if record.get("pattern_id") == pattern_id:
            return record
    raise ValueError(f"unknown pattern ID: {pattern_id}")


def review(
    store: Path,
    *,
    pattern_id: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    if decision not in {"accept", "reject", "retire"}:
        raise ValueError(f"invalid review decision: {decision}")
    record = find_record(store, pattern_id)
    if decision == "accept":
        record["status"] = "accepted_local"
    elif decision == "reject":
        record["status"] = "rejected"
    else:
        record["status"] = "retired"
    record["review"] = {
        "decision": decision,
        "reason": sanitize(reason, 600),
        "reviewed_at": utc_now(),
    }
    write_record(store, record)
    return record


def relevant(
    store: Path,
    *,
    project_root: str | Path | None = None,
    project_types: list[str] | None = None,
    signals: list[str] | None = None,
) -> list[dict[str, Any]]:
    project_id = project_fingerprint(project_root)
    wanted_types = set(normalize_values(project_types))
    wanted_signals = set(normalize_values(signals))
    matches: list[tuple[int, dict[str, Any]]] = []

    for record in load_records(store):
        if record.get("status") != "accepted_local":
            continue
        scope = record.get("scope")
        record_types = set(record.get("project_types", []))
        record_signals = set(record.get("signals", []))
        if scope == "project_specific" and (
            not project_id or project_id not in record.get("project_fingerprints", [])
        ):
            continue
        if scope == "project_family" and not (wanted_types & record_types):
            continue
        if record_signals and not (wanted_signals & record_signals):
            continue
        score = (
            3 * len(wanted_signals & record_signals)
            + 2 * len(wanted_types & record_types)
            + min(int(record.get("occurrence_count", 1)), 5)
        )
        matches.append((score, record))

    matches.sort(key=lambda item: (-item[0], item[1].get("pattern_id", "")))
    return [
        {
            "pattern_id": record["pattern_id"],
            "scope": record["scope"],
            "problem": record["problem"],
            "preferred_response": record["preferred_response"],
            "signals": record.get("signals", []),
            "project_types": record.get("project_types", []),
            "occurrence_count": record.get("occurrence_count", 1),
            "independent_project_count": len(record.get("project_fingerprints", [])),
        }
        for _, record in matches
    ]


def assess_promotion(record: dict[str, Any]) -> dict[str, Any]:
    project_count = len(record.get("project_fingerprints", []))
    evidence_count = len(record.get("evidence_summaries", []))
    repeated = project_count >= 2
    severe_reproduced = (
        record.get("severity") in {"high", "critical"}
        and bool(record.get("reproduced"))
        and evidence_count >= 2
    )
    gates = {
        "accepted_for_local_use": record.get("status") == "accepted_local",
        "not_project_specific": record.get("scope") != "project_specific",
        "has_matching_signals": bool(record.get("signals")),
        "has_generalization_evidence": repeated or severe_reproduced,
        "still_requires_user_approval": True,
        "still_requires_forward_and_regression_tests": True,
    }
    return {
        "pattern_id": record.get("pattern_id"),
        "eligible_for_promotion_review": all(
            gates[key]
            for key in (
                "accepted_for_local_use",
                "not_project_specific",
                "has_matching_signals",
                "has_generalization_evidence",
            )
        ),
        "gates": gates,
        "independent_project_count": project_count,
        "evidence_count": evidence_count,
    }


def mark_promoted(
    store: Path,
    *,
    pattern_id: str,
    target: list[str],
    regression_tests: list[str],
    approval_note: str,
) -> dict[str, Any]:
    record = find_record(store, pattern_id)
    assessment = assess_promotion(record)
    if not assessment["eligible_for_promotion_review"]:
        raise ValueError("promotion gates are not satisfied")
    if not target or not regression_tests:
        raise ValueError("promotion requires target artifacts and regression tests")
    record["status"] = "promoted"
    record["promotion"] = {
        "targets": [sanitize(item, 300) for item in target],
        "regression_tests": [sanitize(item, 300) for item in regression_tests],
        "approval_note": sanitize(approval_note, 600),
        "promoted_at": utc_now(),
    }
    write_record(store, record)
    return record


def load_config(store: Path) -> dict[str, Any]:
    path = store / "config.json"
    if not path.exists():
        return {"capture_mode": "ask"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"capture_mode": "ask"}
    mode = data.get("capture_mode")
    return {"capture_mode": mode if mode in CAPTURE_MODES else "ask"}


def configure(store: Path, capture_mode: str) -> dict[str, str]:
    if capture_mode not in CAPTURE_MODES:
        raise ValueError(f"invalid capture mode: {capture_mode}")
    store.mkdir(parents=True, exist_ok=True)
    config = {"capture_mode": capture_mode}
    (store / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config


def record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "pattern_id": record.get("pattern_id"),
        "status": record.get("status"),
        "scope": record.get("scope"),
        "severity": record.get("severity"),
        "problem": record.get("problem"),
        "project_types": record.get("project_types", []),
        "signals": record.get("signals", []),
        "occurrence_count": record.get("occurrence_count", 1),
        "independent_project_count": len(record.get("project_fingerprints", [])),
        "last_seen_at": record.get("last_seen_at"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, help="Override the private registry path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("configure")
    config_parser.add_argument("--capture-mode", choices=sorted(CAPTURE_MODES), required=True)

    subparsers.add_parser("config")

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--problem", required=True)
    capture_parser.add_argument("--observed-failure", required=True)
    capture_parser.add_argument("--preferred-response", required=True)
    capture_parser.add_argument("--scope", choices=sorted(SCOPES), required=True)
    capture_parser.add_argument("--project-root")
    capture_parser.add_argument("--project-type", action="append", default=[])
    capture_parser.add_argument("--signal", action="append", default=[])
    capture_parser.add_argument("--evidence", action="append", default=[])
    capture_parser.add_argument("--severity", choices=sorted(SEVERITIES), default="medium")
    capture_parser.add_argument("--reproduced", action="store_true")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=sorted(STATUSES))

    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("pattern_id")
    review_parser.add_argument("--decision", choices=("accept", "reject", "retire"), required=True)
    review_parser.add_argument("--reason", required=True)

    relevant_parser = subparsers.add_parser("relevant")
    relevant_parser.add_argument("--project-root")
    relevant_parser.add_argument("--project-type", action="append", default=[])
    relevant_parser.add_argument("--signal", action="append", default=[])

    assess_parser = subparsers.add_parser("assess")
    assess_parser.add_argument("pattern_id")

    promote_parser = subparsers.add_parser("mark-promoted")
    promote_parser.add_argument("pattern_id")
    promote_parser.add_argument("--target", action="append", required=True)
    promote_parser.add_argument("--regression-test", action="append", required=True)
    promote_parser.add_argument("--approval-note", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    store = (args.store or default_store()).expanduser().resolve()

    try:
        if args.command == "configure":
            result: Any = configure(store, args.capture_mode)
        elif args.command == "config":
            result = load_config(store)
        elif args.command == "capture":
            record, created = capture(
                store,
                problem=args.problem,
                observed_failure=args.observed_failure,
                preferred_response=args.preferred_response,
                scope=args.scope,
                project_root=args.project_root,
                project_types=args.project_type,
                signals=args.signal,
                evidence=args.evidence,
                severity=args.severity,
                reproduced=args.reproduced,
            )
            result = {"created": created, "record": record_summary(record)}
        elif args.command == "list":
            records = load_records(store)
            if args.status:
                records = [item for item in records if item.get("status") == args.status]
            result = [record_summary(item) for item in records]
        elif args.command == "review":
            result = record_summary(
                review(
                    store,
                    pattern_id=args.pattern_id,
                    decision=args.decision,
                    reason=args.reason,
                )
            )
        elif args.command == "relevant":
            result = relevant(
                store,
                project_root=args.project_root,
                project_types=args.project_type,
                signals=args.signal,
            )
        elif args.command == "assess":
            result = assess_promotion(find_record(store, args.pattern_id))
        else:
            result = record_summary(
                mark_promoted(
                    store,
                    pattern_id=args.pattern_id,
                    target=args.target,
                    regression_tests=args.regression_test,
                    approval_note=args.approval_note,
                )
            )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
