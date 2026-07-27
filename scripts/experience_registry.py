#!/usr/bin/env python3
"""Manage a private, reviewable learning registry for bootstrap-codex-project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCOPES = {"project_specific", "project_family", "cross_project"}
STATUSES = {"candidate", "accepted_local", "promoted", "rejected", "retired"}
CAPTURE_MODES = {"off", "ask", "auto_sanitized"}
SEVERITIES = {"low", "medium", "high", "critical"}
PATTERN_ID_RE = re.compile(r"^EXP-\d{8}-[0-9a-f]{8}(?:-\d+)?$")
REVIEW_TRANSITIONS = {
    ("candidate", "accept"): "accepted_local",
    ("candidate", "reject"): "rejected",
    ("accepted_local", "retire"): "retired",
    ("promoted", "retire"): "retired",
}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bas_sk_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)
PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)"
)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
MAX_INPUT_LENGTH = 5000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_store() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "learning" / "bootstrap-codex-project"


def sanitize(value: str, limit: int = 1200) -> str:
    if not isinstance(value, str):
        raise ValueError("experience fields must be strings")
    if len(value) > MAX_INPUT_LENGTH:
        raise ValueError(f"experience field exceeds {MAX_INPUT_LENGTH} characters")
    text = value.strip()
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    text = PERSONAL_PATH_RE.sub("<user-home>", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def normalize_values(values: list[str] | None) -> list[str]:
    normalized: set[str] = set()
    for value in values or []:
        clean = sanitize(value, 120).lower()
        if clean:
            normalized.add(clean)
    return sorted(normalized)


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
    project_id: str | None = None,
) -> str:
    payload = "\n".join(
        (
            sanitize(problem).lower(),
            sanitize(preferred_response).lower(),
            scope,
            ",".join(project_types),
            project_id if scope == "project_specific" and project_id else "",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_record(record: dict[str, Any]) -> None:
    required_strings = (
        "pattern_id",
        "status",
        "scope",
        "severity",
        "problem",
        "observed_failure",
        "preferred_response",
        "created_at",
        "last_seen_at",
        "fingerprint",
    )
    for key in required_strings:
        if not isinstance(record.get(key), str) or not record[key]:
            raise ValueError(f"invalid experience record field: {key}")
    if record.get("schema_version") != 1:
        raise ValueError("unsupported experience record schema")
    if not PATTERN_ID_RE.fullmatch(record["pattern_id"]):
        raise ValueError("invalid experience pattern ID")
    if record["status"] not in STATUSES:
        raise ValueError("invalid experience record status")
    if record["scope"] not in SCOPES:
        raise ValueError("invalid experience record scope")
    if record["severity"] not in SEVERITIES:
        raise ValueError("invalid experience record severity")
    if not isinstance(record.get("reproduced"), bool):
        raise ValueError("invalid experience record reproduced flag")
    if not isinstance(record.get("occurrence_count"), int) or record["occurrence_count"] < 1:
        raise ValueError("invalid experience occurrence count")
    if not re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"]):
        raise ValueError("invalid experience fingerprint")
    for key in ("project_types", "signals", "project_fingerprints", "evidence_summaries"):
        values = record.get(key)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError(f"invalid experience record list: {key}")
    if not all(re.fullmatch(r"[0-9a-f]{16}", item) for item in record["project_fingerprints"]):
        raise ValueError("invalid project fingerprint")
    if record.get("review") is not None and not isinstance(record["review"], dict):
        raise ValueError("invalid experience review metadata")
    if record.get("promotion") is not None and not isinstance(record["promotion"], dict):
        raise ValueError("invalid experience promotion metadata")
    conflicts = record.get("conflicts_with", [])
    if not isinstance(conflicts, list) or not all(
        isinstance(item, str) and PATTERN_ID_RE.fullmatch(item) for item in conflicts
    ):
        raise ValueError("invalid experience conflict references")
    superseded_by = record.get("superseded_by")
    if superseded_by is not None and (
        not isinstance(superseded_by, str) or not PATTERN_ID_RE.fullmatch(superseded_by)
    ):
        raise ValueError("invalid experience supersession reference")


def secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def write_private_json(path: Path, value: Any) -> None:
    secure_directory(path.parent)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(value, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path = Path(temporary_name)
        if os.name != "nt":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def load_records(store: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    candidates = store / "candidates"
    if not candidates.exists():
        return records
    for path in sorted(candidates.glob("EXP-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read experience record {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"experience record is not an object: {path.name}")
        validate_record(data)
        if data["pattern_id"] != path.stem:
            raise ValueError(f"experience record ID does not match filename: {path.name}")
        records.append(data)
    return records


def write_record(store: Path, record: dict[str, Any]) -> Path:
    validate_record(record)
    candidates = store / "candidates"
    secure_directory(store)
    secure_directory(candidates)
    path = candidates / f"{record['pattern_id']}.json"
    write_private_json(path, record)
    return path


def records_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("problem", "").lower() != right.get("problem", "").lower():
        return False
    if left.get("preferred_response", "").lower() == right.get("preferred_response", "").lower():
        return False
    if left.get("scope") != right.get("scope"):
        return False
    scope = left.get("scope")
    if scope == "project_specific":
        return bool(
            set(left.get("project_fingerprints", []))
            & set(right.get("project_fingerprints", []))
        )
    if scope == "project_family" and not (
        set(left.get("project_types", [])) & set(right.get("project_types", []))
    ):
        return False
    return bool(set(left.get("signals", [])) & set(right.get("signals", [])))


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
    confirmed: bool = False,
) -> tuple[dict[str, Any], bool]:
    if scope not in SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    if severity not in SEVERITIES:
        raise ValueError(f"invalid severity: {severity}")
    mode = load_config(store)["capture_mode"]
    if mode == "off":
        raise ValueError("experience capture is disabled")
    if mode == "ask" and not confirmed:
        raise ValueError("capture mode is ask; current user confirmation is required")

    clean_problem = sanitize(problem)
    clean_failure = sanitize(observed_failure)
    clean_preferred = sanitize(preferred_response)
    if not clean_problem or not clean_failure or not clean_preferred:
        raise ValueError("problem, observed failure, and preferred response are required")
    clean_types = normalize_values(project_types)
    clean_signals = normalize_values(signals)
    project_id = project_fingerprint(project_root)
    if scope == "project_specific" and not project_id:
        raise ValueError("project_specific capture requires project_root")
    if scope == "project_family" and not clean_types:
        raise ValueError("project_family capture requires at least one project type")
    if scope != "project_specific" and not clean_signals:
        raise ValueError("reusable experience requires at least one matching signal")
    fingerprint = candidate_fingerprint(
        clean_problem,
        clean_preferred,
        scope,
        clean_types,
        project_id,
    )
    now = utc_now()
    records = load_records(store)

    for record in records:
        if record.get("fingerprint") != fingerprint:
            continue
        record["last_seen_at"] = now
        record["occurrence_count"] = int(record.get("occurrence_count", 1)) + 1
        if project_id:
            projects = set(record.get("project_fingerprints", []))
            projects.add(project_id)
            record["project_fingerprints"] = sorted(projects)
        record["signals"] = sorted(
            set(record.get("signals", [])) | set(clean_signals)
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
    existing_ids = {item.get("pattern_id") for item in records}
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
        "observed_failure": clean_failure,
        "preferred_response": clean_preferred,
        "project_types": clean_types,
        "signals": clean_signals,
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
        "conflicts_with": [],
        "superseded_by": None,
    }
    record["conflicts_with"] = sorted(
        item["pattern_id"]
        for item in records
        if item.get("status") in {"candidate", "accepted_local", "promoted"}
        and records_conflict(record, item)
    )
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
    supersedes: list[str] | None = None,
) -> dict[str, Any]:
    if decision not in {"accept", "reject", "retire"}:
        raise ValueError(f"invalid review decision: {decision}")
    record = find_record(store, pattern_id)
    transition = (record["status"], decision)
    if transition not in REVIEW_TRANSITIONS:
        raise ValueError(
            f"invalid experience transition: {record['status']} -> {decision}"
        )
    clean_reason = sanitize(reason, 600)
    if not clean_reason:
        raise ValueError("review reason is required")
    requested_supersession = set(supersedes or [])
    if decision != "accept" and requested_supersession:
        raise ValueError("supersedes is valid only when accepting a candidate")
    if decision == "accept":
        records_by_id = {item["pattern_id"]: item for item in load_records(store)}
        conflict_ids = set(record.get("conflicts_with", []))
        invalid_targets = requested_supersession - conflict_ids
        if invalid_targets:
            raise ValueError(
                "supersedes must reference detected conflicts: "
                + ", ".join(sorted(invalid_targets))
            )
        promoted_conflicts = sorted(
            conflict_id
            for conflict_id in conflict_ids
            if records_by_id.get(conflict_id, {}).get("status") == "promoted"
        )
        if promoted_conflicts:
            raise ValueError(
                "a local review cannot supersede promoted Skill experience: "
                + ", ".join(promoted_conflicts)
            )
        required_supersession = {
            conflict_id
            for conflict_id in conflict_ids
            if records_by_id.get(conflict_id, {}).get("status") == "accepted_local"
        }
        if requested_supersession != required_supersession:
            raise ValueError(
                "accepting this conflict requires supersedes: "
                + (", ".join(sorted(required_supersession)) or "none")
            )
        for conflict_id in sorted(requested_supersession):
            previous = records_by_id[conflict_id]
            previous["status"] = "retired"
            previous["superseded_by"] = record["pattern_id"]
            previous["review"] = {
                "decision": "retire",
                "reason": f"Superseded by {record['pattern_id']}: {clean_reason}",
                "reviewed_at": utc_now(),
            }
            write_record(store, previous)
    record["status"] = REVIEW_TRANSITIONS[transition]
    record["review"] = {
        "decision": decision,
        "reason": clean_reason,
        "reviewed_at": utc_now(),
        "supersedes": sorted(requested_supersession),
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
        if scope in {"project_family", "cross_project"} and not record_signals:
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
        "requires_current_user_approval": True,
        "requires_passed_forward_tests": True,
        "requires_passed_regression_tests": True,
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
    forward_tests: list[str],
    regression_tests: list[str],
    approval_note: str,
    user_approved: bool,
) -> dict[str, Any]:
    record = find_record(store, pattern_id)
    assessment = assess_promotion(record)
    if not assessment["eligible_for_promotion_review"]:
        raise ValueError("promotion gates are not satisfied")
    if record["status"] != "accepted_local":
        raise ValueError("only accepted_local experience can be promoted")
    if not user_approved:
        raise ValueError("promotion requires current explicit user approval")
    clean_approval = sanitize(approval_note, 600)
    if len(clean_approval) < 12:
        raise ValueError("promotion approval note must state the approved change")
    clean_targets = [sanitize(item, 300) for item in target if sanitize(item, 300)]
    clean_forward = [sanitize(item, 300) for item in forward_tests if sanitize(item, 300)]
    clean_regression = [
        sanitize(item, 300) for item in regression_tests if sanitize(item, 300)
    ]
    if not clean_targets or not clean_forward or not clean_regression:
        raise ValueError(
            "promotion requires targets, passed forward tests, and passed regression tests"
        )
    passed_marker = re.compile(r"(?i)(?:\bpassed\b|\bexit(?:_code)?\s*=\s*0\b)")
    if not all(passed_marker.search(item) for item in clean_forward + clean_regression):
        raise ValueError("each promotion test must include a passed or exit=0 result")
    record["status"] = "promoted"
    record["promotion"] = {
        "targets": clean_targets,
        "forward_tests": clean_forward,
        "regression_tests": clean_regression,
        "user_approved": True,
        "approval_note": clean_approval,
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
    config = {"capture_mode": capture_mode}
    write_private_json(store / "config.json", config)
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
        "conflicts_with": record.get("conflicts_with", []),
        "superseded_by": record.get("superseded_by"),
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
    capture_parser.add_argument(
        "--confirm-capture",
        action="store_true",
        help="Record current user confirmation when capture mode is ask",
    )

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=sorted(STATUSES))

    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("pattern_id")
    review_parser.add_argument("--decision", choices=("accept", "reject", "retire"), required=True)
    review_parser.add_argument("--reason", required=True)
    review_parser.add_argument(
        "--supersedes",
        action="append",
        default=[],
        help="Accepted local pattern ID retired by this conflicting candidate",
    )

    relevant_parser = subparsers.add_parser("relevant")
    relevant_parser.add_argument("--project-root")
    relevant_parser.add_argument("--project-type", action="append", default=[])
    relevant_parser.add_argument("--signal", action="append", default=[])

    assess_parser = subparsers.add_parser("assess")
    assess_parser.add_argument("pattern_id")

    promote_parser = subparsers.add_parser("mark-promoted")
    promote_parser.add_argument("pattern_id")
    promote_parser.add_argument("--target", action="append", required=True)
    promote_parser.add_argument("--forward-test", action="append", required=True)
    promote_parser.add_argument("--regression-test", action="append", required=True)
    promote_parser.add_argument("--approval-note", required=True)
    promote_parser.add_argument(
        "--user-approved",
        action="store_true",
        help="Assert that the current user explicitly approved this promotion",
    )
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
                confirmed=args.confirm_capture,
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
                    supersedes=args.supersedes,
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
                    forward_tests=args.forward_test,
                    regression_tests=args.regression_test,
                    approval_note=args.approval_note,
                    user_approved=args.user_approved,
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
