#!/usr/bin/env python3
"""Maintain the bounded deliberate-project experience catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator


NAMESPACE = "deliberate-project"
DATABASE_NAME = "experience.sqlite3"
SCHEMA_VERSION = 2
STATUSES = {
    "Candidate",
    "Shadow",
    "Active",
    "Deprecated",
    "Expired",
    "Conflicted",
    "Rolled-back",
}
USABLE_STATUSES = {"Shadow", "Active"}
TERMINAL_STATUSES = {"Deprecated", "Expired", "Rolled-back"}
OUTCOMES = {"candidate", "shadow-benefit", "shadow-regression", "conflict"}
VERIFICATION_STATES = {"Verified", "Legacy-attested", "Unverified"}
OBSERVATION_OUTCOMES = {
    "Candidate": {"candidate"},
    "Shadow": {"shadow-benefit", "shadow-regression", "conflict"},
    "Active": {"shadow-regression", "conflict"},
    "Conflicted": set(),
    "Deprecated": set(),
    "Expired": set(),
    "Rolled-back": set(),
}
ALLOWED_TRANSITIONS = {
    "Candidate": {"Shadow", "Expired", "Deprecated"},
    "Shadow": {"Active", "Conflicted", "Rolled-back", "Expired", "Deprecated"},
    "Active": {"Conflicted", "Rolled-back", "Expired", "Deprecated"},
    "Conflicted": {
        "Candidate",
        "Shadow",
        "Active",
        "Deprecated",
        "Rolled-back",
        "Expired",
    },
    "Deprecated": set(),
    "Expired": set(),
    "Rolled-back": set(),
}
SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
LESSON_ID = re.compile(r"^[a-f0-9]{24}$")
SAFE_SOURCE = re.compile(
    r"^(?:hash:[A-Fa-f0-9]{16,128}|source:[A-Za-z0-9._:-]{1,256}|"
    r"standard:[A-Za-z0-9._:/-]{1,256}|public:https://\S{1,2020})$"
)


class CatalogError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def checked_text(value: str, field: str, max_length: int) -> str:
    value = value.strip()
    if not value:
        raise CatalogError(f"{field} is required")
    if "\x00" in value or len(value) > max_length:
        raise CatalogError(f"{field} is invalid or exceeds {max_length} characters")
    return value


def checked_safe_id(value: str, field: str) -> str:
    value = value.strip()
    if not SAFE_ID.fullmatch(value):
        raise CatalogError(f"{field} must match [A-Za-z0-9._:-]{{1,128}}")
    return value


def checked_case_id(value: str) -> str:
    return checked_safe_id(value, "case_id")


def checked_expiry(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CatalogError("expires_at must be YYYY-MM-DD") from exc
    return parsed.isoformat()


def checked_source(value: str) -> str:
    value = checked_text(value, "source", 2048)
    if not SAFE_SOURCE.fullmatch(value):
        raise CatalogError(
            "source must use hash:, source:, standard:, or public:https://"
        )
    return value


def checked_lesson_id(value: str, field: str = "lesson_id") -> str:
    value = value.strip()
    if not LESSON_ID.fullmatch(value):
        raise CatalogError(f"{field} must be a 24-character lowercase hex ID")
    return value


def checked_evidence_ids(values: list[str]) -> list[str]:
    if not values or len(values) > 20:
        raise CatalogError("provide between 1 and 20 evidence IDs")
    return [checked_safe_id(value, "evidence_id") for value in values]


def host_config_root() -> str | None:
    explicit_config = os.environ.get("DELIBERATE_PROJECT_EXPERIENCE_CONFIG")
    if explicit_config:
        config_path = Path(explicit_config).expanduser()
    else:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        config_path = codex_home / "deliberate-project-experience-root.txt"
    if not config_path.exists():
        return None
    if not config_path.is_file() or config_path.is_symlink():
        raise CatalogError("experience root config must be a regular non-link file")
    configured = config_path.read_text(encoding="utf-8").strip()
    if not configured or "\x00" in configured or "\n" in configured or len(configured) > 4096:
        raise CatalogError("experience root config must contain one valid path")
    return configured


def resolve_root() -> Path:
    configured = host_config_root() or os.environ.get(
        "AEGOS_SKILLS_EXPERIENCE_ROOT"
    )
    if not configured:
        raise CatalogError("experience root is not configured")
    root = Path(configured).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise CatalogError("configured experience root is not a directory")
    return root


def namespace_path(root: Path, create: bool) -> Path:
    namespace = (root / NAMESPACE).resolve(strict=False)
    try:
        namespace.relative_to(root)
    except ValueError as exc:
        raise CatalogError("catalog namespace escapes configured root") from exc
    if create:
        namespace.mkdir(mode=0o700, parents=False, exist_ok=True)
    if namespace.exists() and not namespace.is_dir():
        raise CatalogError("catalog namespace is not a directory")
    return namespace


def database_path(create: bool) -> Path:
    root = resolve_root()
    if create and not os.access(root, os.W_OK):
        raise CatalogError("configured experience root is not writable")
    path = namespace_path(root, create) / DATABASE_NAME
    if path.is_symlink():
        raise CatalogError("catalog database must not be a symbolic link")
    if path.exists():
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise CatalogError("catalog database escapes configured root") from exc
        if not resolved.is_file():
            raise CatalogError("catalog database is not a regular file")
    return path


def connect(
    path: Path,
    writable: bool,
    create: bool = False,
    allow_legacy_read: bool = False,
) -> sqlite3.Connection:
    if not path.exists() and not create:
        raise CatalogError("experience catalog does not exist")
    if writable:
        connection = sqlite3.connect(path, timeout=10.0)
    else:
        connection = sqlite3.connect(
            f"{path.resolve(strict=True).as_uri()}?mode=ro", timeout=10.0, uri=True
        )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    if writable:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        initialize(connection)
    else:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION and not allow_legacy_read:
            connection.close()
            if version == 1:
                raise CatalogError("catalog schema 1 requires the migrate command")
            raise CatalogError(f"unsupported catalog schema version: {version}")
    return connection


def create_schema_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            lesson_id TEXT PRIMARY KEY,
            claim TEXT NOT NULL,
            scope TEXT NOT NULL,
            version_scope TEXT NOT NULL,
            jurisdiction TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            recheck_trigger TEXT NOT NULL,
            limitations TEXT NOT NULL,
            high_risk_fix INTEGER NOT NULL CHECK (high_risk_fix IN (0, 1)),
            status TEXT NOT NULL CHECK (status IN (
                'Candidate', 'Shadow', 'Active', 'Deprecated',
                'Expired', 'Conflicted', 'Rolled-back'
            )),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            case_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN (
                'candidate', 'shadow-benefit', 'shadow-regression', 'conflict'
            )),
            source_lineage_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            verification_state TEXT NOT NULL CHECK (verification_state IN (
                'Verified', 'Legacy-attested', 'Unverified'
            )),
            verification_method TEXT NOT NULL,
            privacy_reviewed INTEGER NOT NULL CHECK (privacy_reviewed IN (0, 1)),
            license_reviewed INTEGER NOT NULL CHECK (license_reviewed IN (0, 1)),
            status_at_observation TEXT NOT NULL,
            note TEXT NOT NULL,
            related_lesson_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (lesson_id, case_id, outcome)
        );
        CREATE TABLE IF NOT EXISTS transitions (
            transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conflict_resolutions (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            second_lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            action TEXT NOT NULL CHECK (action IN (
                'keep-first', 'keep-second', 'retire-both', 'continue-isolation'
            )),
            reason TEXT NOT NULL,
            source_lineage_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            verification_state TEXT NOT NULL,
            verification_method TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        PRAGMA user_version = 2;
        """
    )


def migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        BEGIN IMMEDIATE;
        ALTER TABLE observations ADD COLUMN evidence_ids_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE observations ADD COLUMN snapshot_id TEXT NOT NULL DEFAULT 'legacy-v1';
        ALTER TABLE observations ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'Legacy-attested';
        ALTER TABLE observations ADD COLUMN verification_method TEXT NOT NULL DEFAULT 'v1-required-review-flags';
        ALTER TABLE observations ADD COLUMN privacy_reviewed INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE observations ADD COLUMN license_reviewed INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE observations ADD COLUMN status_at_observation TEXT NOT NULL DEFAULT 'Candidate';
        UPDATE observations
        SET evidence_ids_json = '["legacy:observation:' || observation_id || '"]',
            status_at_observation = CASE outcome
                WHEN 'candidate' THEN 'Candidate'
                WHEN 'shadow-benefit' THEN 'Shadow'
                WHEN 'shadow-regression' THEN 'Shadow'
                WHEN 'conflict' THEN 'Shadow'
                ELSE 'Candidate'
            END;
        CREATE TABLE IF NOT EXISTS conflict_resolutions (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            second_lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
            action TEXT NOT NULL CHECK (action IN (
                'keep-first', 'keep-second', 'retire-both', 'continue-isolation'
            )),
            reason TEXT NOT NULL,
            source_lineage_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            verification_state TEXT NOT NULL,
            verification_method TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        PRAGMA user_version = 2;
        COMMIT;
        """
    )


def initialize(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        create_schema_v2(connection)
    elif version == 1:
        migrate_v1_to_v2(connection)
    elif version != SCHEMA_VERSION:
        raise CatalogError(f"unsupported catalog schema version: {version}")


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def lesson_id_for(
    claim: str,
    scope: str,
    version_scope: str,
    jurisdiction: str,
    expires_at: str,
    recheck_trigger: str,
    limitations: str,
) -> str:
    canonical = json.dumps(
        [
            claim,
            scope,
            version_scope,
            jurisdiction,
            expires_at,
            recheck_trigger,
            limitations,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def transition(
    connection: sqlite3.Connection,
    lesson_id: str,
    new_status: str,
    reason: str,
    now: str,
) -> tuple[str, str]:
    if new_status not in STATUSES:
        raise CatalogError(f"unsupported status: {new_status}")
    row = connection.execute(
        "SELECT status FROM lessons WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    if row is None:
        raise CatalogError(f"unknown lesson_id: {lesson_id}")
    old_status = row["status"]
    if old_status == new_status:
        return old_status, new_status
    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise CatalogError(f"illegal status transition: {old_status} -> {new_status}")
    connection.execute(
        "UPDATE lessons SET status = ?, updated_at = ? WHERE lesson_id = ?",
        (new_status, now, lesson_id),
    )
    connection.execute(
        "INSERT INTO transitions (lesson_id, from_status, to_status, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (lesson_id, old_status, new_status, reason, now),
    )
    return old_status, new_status


def effective_status(status: str, expires_at: str) -> str:
    if expires_at < date.today().isoformat() and status not in TERMINAL_STATUSES:
        return "Expired"
    return status


def expire_if_needed(connection: sqlite3.Connection, lesson_id: str, now: str) -> None:
    row = connection.execute(
        "SELECT expires_at, status FROM lessons WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    if row and effective_status(row["status"], row["expires_at"]) == "Expired" and row[
        "status"
    ] != "Expired":
        transition(connection, lesson_id, "Expired", "expiry date reached", now)


def counts(
    connection: sqlite3.Connection, lesson_id: str, verified_only: bool
) -> dict[str, int]:
    query = (
        "SELECT outcome, COUNT(DISTINCT case_id) AS count FROM observations "
        "WHERE lesson_id = ?"
    )
    params: tuple[object, ...] = (lesson_id,)
    if verified_only:
        query += " AND verification_state = 'Verified'"
    query += " GROUP BY outcome"
    rows = connection.execute(query, params).fetchall()
    result = {outcome: 0 for outcome in OUTCOMES}
    result.update({row["outcome"]: row["count"] for row in rows})
    return result


def independent_lineage_count(
    connection: sqlite3.Connection,
    lesson_id: str,
    outcome: str,
    status_at_observation: str | None = None,
) -> int:
    query = (
        "SELECT case_id, source_lineage_json FROM observations "
        "WHERE lesson_id = ? AND outcome = ? AND verification_state = 'Verified'"
    )
    params: list[object] = [lesson_id, outcome]
    if status_at_observation is not None:
        query += " AND status_at_observation = ?"
        params.append(status_at_observation)
    rows = connection.execute(query, tuple(params)).fetchall()

    # Shared locators connect observations into one upstream lineage component.
    components: list[set[str]] = []
    for row in rows:
        sources = set(json.loads(row["source_lineage_json"]))
        touching = [item for item in components if item & sources]
        if not touching:
            components.append(sources)
            continue
        merged = set(sources)
        for item in touching:
            merged.update(item)
            components.remove(item)
        components.append(merged)
    return len(components)


def shadow_benefit_count(connection: sqlite3.Connection, lesson_id: str) -> int:
    row = connection.execute(
        "SELECT COUNT(DISTINCT case_id) FROM observations "
        "WHERE lesson_id = ? AND outcome = 'shadow-benefit' "
        "AND verification_state = 'Verified' AND status_at_observation = 'Shadow'",
        (lesson_id,),
    ).fetchone()
    return int(row[0])


def fetch_lesson(connection: sqlite3.Connection, lesson_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    if row is None:
        raise CatalogError(f"unknown lesson_id: {lesson_id}")
    result = dict(row)
    result["effective_status"] = effective_status(row["status"], row["expires_at"])
    result["verified_observation_counts"] = counts(connection, lesson_id, True)
    result["all_observation_counts"] = counts(connection, lesson_id, False)
    result["verified_shadow_benefit_cases"] = shadow_benefit_count(
        connection, lesson_id
    )
    result["verified_independent_candidate_lineages"] = independent_lineage_count(
        connection, lesson_id, "candidate"
    )
    result["verified_independent_shadow_benefit_lineages"] = (
        independent_lineage_count(
            connection, lesson_id, "shadow-benefit", "Shadow"
        )
    )
    return result


def validate_observation_state(status: str, outcome: str) -> None:
    if outcome not in OBSERVATION_OUTCOMES[status]:
        allowed = sorted(OBSERVATION_OUTCOMES[status])
        rendered = ", ".join(allowed) if allowed else "none"
        raise CatalogError(
            f"outcome {outcome} is invalid for {status}; allowed outcomes: {rendered}"
        )


def observation_exists(
    connection: sqlite3.Connection, lesson_id: str, case_id: str, outcome: str
) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM observations WHERE lesson_id = ? AND case_id = ? "
            "AND outcome = ?",
            (lesson_id, case_id, outcome),
        ).fetchone()
        is not None
    )


def insert_observation(
    connection: sqlite3.Connection,
    *,
    lesson_id: str,
    case_id: str,
    outcome: str,
    sources: list[str],
    evidence_ids: list[str],
    snapshot_id: str,
    verification_method: str,
    status_at_observation: str,
    related_lesson_id: str | None,
    now: str,
) -> None:
    connection.execute(
        "INSERT INTO observations "
        "(lesson_id, case_id, outcome, source_lineage_json, evidence_ids_json, "
        "snapshot_id, verification_state, verification_method, privacy_reviewed, "
        "license_reviewed, status_at_observation, note, related_lesson_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Verified', ?, 1, 1, ?, '', ?, ?)",
        (
            lesson_id,
            case_id,
            outcome,
            json.dumps(sources, ensure_ascii=False),
            json.dumps(evidence_ids, ensure_ascii=False),
            snapshot_id,
            verification_method,
            status_at_observation,
            related_lesson_id,
            now,
        ),
    )


def observe(args: argparse.Namespace) -> dict[str, object]:
    if not args.privacy_reviewed or not args.license_reviewed or not args.verified:
        raise CatalogError(
            "verified, privacy-reviewed, and license-reviewed flags are required"
        )
    claim = checked_text(args.claim, "claim", 2000)
    scope = checked_text(args.scope, "scope", 1000)
    version_scope = checked_text(args.version_scope, "version_scope", 300)
    jurisdiction = checked_text(args.jurisdiction, "jurisdiction", 300)
    expires_at = checked_expiry(args.expires_at)
    recheck_trigger = checked_text(args.recheck_trigger, "recheck_trigger", 1000)
    limitations = checked_text(args.limitations, "limitations", 1000)
    case_id = checked_case_id(args.case_id)
    sources = sorted({checked_source(item) for item in args.source})
    if not sources or len(sources) > 20:
        raise CatalogError("provide between 1 and 20 safe source locators")
    evidence_ids = checked_evidence_ids(args.evidence_id)
    snapshot_id = checked_safe_id(args.snapshot_id, "snapshot_id")
    verification_method = checked_text(
        args.verification_method, "verification_method", 500
    )
    if args.high_risk_fix and args.outcome != "candidate":
        raise CatalogError("high-risk-fix is valid only for a candidate observation")
    if args.outcome == "conflict" and not args.related_lesson_id:
        raise CatalogError("conflict outcome requires related_lesson_id")
    if args.outcome != "conflict" and args.related_lesson_id:
        raise CatalogError("related_lesson_id is valid only for conflict outcomes")
    related_lesson_id = (
        checked_lesson_id(args.related_lesson_id, "related_lesson_id")
        if args.related_lesson_id
        else None
    )

    lesson_id = lesson_id_for(
        claim,
        scope,
        version_scope,
        jurisdiction,
        expires_at,
        recheck_trigger,
        limitations,
    )
    if related_lesson_id == lesson_id:
        raise CatalogError("a lesson cannot conflict with itself")
    path = database_path(create=True)
    now = utc_now()
    connection = connect(path, writable=True, create=True)
    try:
        with transaction(connection):
            existing = connection.execute(
                "SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)
            ).fetchone()
            if existing is None:
                if args.outcome != "candidate":
                    raise CatalogError("a new lesson must start with a candidate observation")
                connection.execute(
                    "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        lesson_id,
                        claim,
                        scope,
                        version_scope,
                        jurisdiction,
                        expires_at,
                        recheck_trigger,
                        limitations,
                        int(args.high_risk_fix),
                        "Candidate",
                        now,
                        now,
                    ),
                )
                before_status = "Candidate"
            else:
                immutable = (
                    "claim",
                    "scope",
                    "version_scope",
                    "jurisdiction",
                    "expires_at",
                    "recheck_trigger",
                    "limitations",
                )
                expected = (
                    claim,
                    scope,
                    version_scope,
                    jurisdiction,
                    expires_at,
                    recheck_trigger,
                    limitations,
                )
                if tuple(existing[field] for field in immutable) != expected:
                    raise CatalogError(
                        "lesson identity collision or attempted semantic overwrite"
                    )
                before_status = existing["status"]

            if observation_exists(connection, lesson_id, case_id, args.outcome):
                result = fetch_lesson(connection, lesson_id)
                result.update(
                    {
                        "before_status": before_status,
                        "after_status": result["status"],
                        "catalog_path": str(path),
                        "recorded_outcome": args.outcome,
                        "case_id": case_id,
                        "duplicate": True,
                        "changed": False,
                    }
                )
                return result
            validate_observation_state(before_status, args.outcome)

            related_status: str | None = None
            if args.outcome == "conflict":
                related = connection.execute(
                    "SELECT status FROM lessons WHERE lesson_id = ?",
                    (related_lesson_id,),
                ).fetchone()
                if related is None:
                    raise CatalogError("related conflict lesson does not exist")
                related_status = related["status"]
                if related_status not in {"Shadow", "Active"}:
                    raise CatalogError(
                        "a related conflict lesson must be Shadow or Active"
                    )
                if observation_exists(
                    connection, related_lesson_id, case_id, args.outcome
                ):
                    raise CatalogError(
                        "related lesson already has this conflict case observation"
                    )

            if args.high_risk_fix:
                connection.execute(
                    "UPDATE lessons SET high_risk_fix = 1, updated_at = ? "
                    "WHERE lesson_id = ?",
                    (now, lesson_id),
                )

            insert_observation(
                connection,
                lesson_id=lesson_id,
                case_id=case_id,
                outcome=args.outcome,
                sources=sources,
                evidence_ids=evidence_ids,
                snapshot_id=snapshot_id,
                verification_method=verification_method,
                status_at_observation=before_status,
                related_lesson_id=related_lesson_id,
                now=now,
            )

            if args.outcome == "conflict":
                insert_observation(
                    connection,
                    lesson_id=related_lesson_id,
                    case_id=case_id,
                    outcome=args.outcome,
                    sources=sources,
                    evidence_ids=evidence_ids,
                    snapshot_id=snapshot_id,
                    verification_method=verification_method,
                    status_at_observation=related_status,
                    related_lesson_id=lesson_id,
                    now=now,
                )
                transition(
                    connection, lesson_id, "Conflicted", "unresolved true conflict", now
                )
                transition(
                    connection,
                    related_lesson_id,
                    "Conflicted",
                    f"conflicts with {lesson_id}",
                    now,
                )
            elif args.outcome == "shadow-regression":
                transition(
                    connection, lesson_id, "Rolled-back", "verified regression", now
                )
            elif args.outcome == "candidate":
                current = connection.execute(
                    "SELECT high_risk_fix FROM lessons WHERE lesson_id = ?",
                    (lesson_id,),
                ).fetchone()
                candidate_count = counts(connection, lesson_id, True)["candidate"]
                independent_count = independent_lineage_count(
                    connection, lesson_id, "candidate"
                )
                if current["high_risk_fix"] or independent_count >= 2:
                    reason = (
                        "verified high-risk fix entered Shadow"
                        if current["high_risk_fix"] and candidate_count < 2
                        else "independent case and source-lineage gate satisfied"
                    )
                    transition(connection, lesson_id, "Shadow", reason, now)
            elif args.outcome == "shadow-benefit":
                if independent_lineage_count(
                    connection, lesson_id, "shadow-benefit", "Shadow"
                ) >= 2:
                    transition(
                        connection,
                        lesson_id,
                        "Active",
                        "two independent verified post-Shadow benefit cases satisfied",
                        now,
                    )

            expire_if_needed(connection, lesson_id, now)
            result = fetch_lesson(connection, lesson_id)
            result.update(
                {
                    "before_status": before_status,
                    "after_status": result["status"],
                    "catalog_path": str(path),
                    "recorded_outcome": args.outcome,
                    "case_id": case_id,
                    "duplicate": False,
                    "changed": True,
                }
            )
            return result
    finally:
        connection.close()


def list_lessons(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(create=False)
    connection = connect(path, writable=False)
    try:
        rows = connection.execute(
            "SELECT lesson_id, claim, scope, status, expires_at, updated_at "
            "FROM lessons ORDER BY updated_at DESC, lesson_id"
        ).fetchall()
        lessons = []
        for row in rows:
            item = dict(row)
            item["effective_status"] = effective_status(
                row["status"], row["expires_at"]
            )
            if args.status and item["effective_status"] != args.status:
                continue
            lessons.append(item)
        return {"catalog_path": str(path), "lessons": lessons}
    finally:
        connection.close()


def load_lessons(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(create=False)
    connection = connect(path, writable=False)
    try:
        rows = connection.execute(
            "SELECT lesson_id FROM lessons WHERE status IN ('Shadow', 'Active') "
            "AND expires_at >= ? ORDER BY updated_at DESC, lesson_id",
            (date.today().isoformat(),),
        ).fetchall()
        lessons = []
        for row in rows:
            item = fetch_lesson(connection, row["lesson_id"])
            item["permitted_use"] = (
                "routing-hint" if item["status"] == "Active" else "method-suggestion-only"
            )
            lessons.append(item)
        return {
            "catalog_path": str(path),
            "lessons": lessons,
            "applicability_filter_required": True,
        }
    finally:
        connection.close()


def parse_json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def show_lesson(args: argparse.Namespace) -> dict[str, object]:
    lesson_id = checked_lesson_id(args.lesson_id)
    path = database_path(create=False)
    connection = connect(path, writable=False)
    try:
        result = fetch_lesson(connection, lesson_id)
        result["catalog_path"] = str(path)
        result["observations"] = []
        for row in connection.execute(
            "SELECT observation_id, case_id, outcome, source_lineage_json, "
            "evidence_ids_json, snapshot_id, verification_state, verification_method, "
            "privacy_reviewed, license_reviewed, status_at_observation, "
            "related_lesson_id, created_at FROM observations WHERE lesson_id = ? "
            "ORDER BY observation_id",
            (lesson_id,),
        ):
            item = dict(row)
            item["source_lineage"] = parse_json_list(item.pop("source_lineage_json"))
            item["evidence_ids"] = parse_json_list(item.pop("evidence_ids_json"))
            item["privacy_reviewed"] = bool(item["privacy_reviewed"])
            item["license_reviewed"] = bool(item["license_reviewed"])
            result["observations"].append(item)
        result["transitions"] = [
            dict(row)
            for row in connection.execute(
                "SELECT from_status, to_status, reason, created_at FROM transitions "
                "WHERE lesson_id = ? ORDER BY transition_id",
                (lesson_id,),
            )
        ]
        result["conflict_resolutions"] = []
        for row in connection.execute(
            "SELECT * FROM conflict_resolutions WHERE first_lesson_id = ? "
            "OR second_lesson_id = ? ORDER BY resolution_id",
            (lesson_id, lesson_id),
        ):
            item = dict(row)
            item["source_lineage"] = parse_json_list(item.pop("source_lineage_json"))
            item["evidence_ids"] = parse_json_list(item.pop("evidence_ids_json"))
            result["conflict_resolutions"].append(item)
        return result
    finally:
        connection.close()


def prior_conflict_status(connection: sqlite3.Connection, lesson_id: str) -> str:
    row = connection.execute(
        "SELECT from_status FROM transitions WHERE lesson_id = ? "
        "AND to_status = 'Conflicted' ORDER BY transition_id DESC LIMIT 1",
        (lesson_id,),
    ).fetchone()
    if row is None or row["from_status"] not in {"Candidate", "Shadow", "Active"}:
        raise CatalogError(f"cannot restore pre-conflict status for {lesson_id}")
    return row["from_status"]


def resolve_conflict(args: argparse.Namespace) -> dict[str, object]:
    if not args.privacy_reviewed or not args.license_reviewed or not args.verified:
        raise CatalogError(
            "verified, privacy-reviewed, and license-reviewed flags are required"
        )
    first_id = checked_lesson_id(args.lesson_id)
    second_id = checked_lesson_id(args.related_lesson_id, "related_lesson_id")
    if first_id == second_id:
        raise CatalogError("conflict resolution requires two different lessons")
    reason = checked_text(args.reason, "reason", 1000)
    sources = [checked_source(item) for item in args.source]
    if not sources or len(sources) > 20:
        raise CatalogError("provide between 1 and 20 safe source locators")
    evidence_ids = checked_evidence_ids(args.evidence_id)
    snapshot_id = checked_safe_id(args.snapshot_id, "snapshot_id")
    verification_method = checked_text(
        args.verification_method, "verification_method", 500
    )
    path = database_path(create=False)
    connection = connect(path, writable=True)
    now = utc_now()
    try:
        with transaction(connection):
            first = connection.execute(
                "SELECT status FROM lessons WHERE lesson_id = ?", (first_id,)
            ).fetchone()
            second = connection.execute(
                "SELECT status FROM lessons WHERE lesson_id = ?", (second_id,)
            ).fetchone()
            if first is None or second is None:
                raise CatalogError("both conflict lessons must exist")
            if first["status"] != "Conflicted" or second["status"] != "Conflicted":
                raise CatalogError("both lessons must currently be Conflicted")
            linked = connection.execute(
                "SELECT 1 FROM observations WHERE outcome = 'conflict' AND "
                "((lesson_id = ? AND related_lesson_id = ?) OR "
                "(lesson_id = ? AND related_lesson_id = ?)) LIMIT 1",
                (first_id, second_id, second_id, first_id),
            ).fetchone()
            if linked is None:
                raise CatalogError("lessons do not have a recorded conflict relationship")

            if args.action == "keep-first":
                transition(
                    connection,
                    first_id,
                    prior_conflict_status(connection, first_id),
                    f"conflict resolved; retained: {reason}",
                    now,
                )
                transition(
                    connection,
                    second_id,
                    "Deprecated",
                    f"superseded by {first_id}: {reason}",
                    now,
                )
            elif args.action == "keep-second":
                transition(
                    connection,
                    second_id,
                    prior_conflict_status(connection, second_id),
                    f"conflict resolved; retained: {reason}",
                    now,
                )
                transition(
                    connection,
                    first_id,
                    "Deprecated",
                    f"superseded by {second_id}: {reason}",
                    now,
                )
            elif args.action == "retire-both":
                transition(
                    connection, first_id, "Deprecated", f"conflict retired: {reason}", now
                )
                transition(
                    connection, second_id, "Deprecated", f"conflict retired: {reason}", now
                )
            elif args.action != "continue-isolation":
                raise CatalogError(f"unsupported conflict action: {args.action}")

            connection.execute(
                "INSERT INTO conflict_resolutions "
                "(first_lesson_id, second_lesson_id, action, reason, "
                "source_lineage_json, evidence_ids_json, snapshot_id, "
                "verification_state, verification_method, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'Verified', ?, ?)",
                (
                    first_id,
                    second_id,
                    args.action,
                    reason,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(evidence_ids, ensure_ascii=False),
                    snapshot_id,
                    verification_method,
                    now,
                ),
            )
            return {
                "catalog_path": str(path),
                "action": args.action,
                "first_lesson": fetch_lesson(connection, first_id),
                "second_lesson": fetch_lesson(connection, second_id),
            }
    finally:
        connection.close()


def retire(args: argparse.Namespace) -> dict[str, object]:
    lesson_id = checked_lesson_id(args.lesson_id)
    reason = checked_text(args.reason, "reason", 1000)
    path = database_path(create=False)
    connection = connect(path, writable=True)
    now = utc_now()
    try:
        with transaction(connection):
            before, after = transition(connection, lesson_id, args.target, reason, now)
            result = fetch_lesson(connection, lesson_id)
            result.update(
                {"before_status": before, "after_status": after, "catalog_path": str(path)}
            )
            return result
    finally:
        connection.close()


def refresh(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(create=False)
    connection = connect(path, writable=True)
    now = utc_now()
    changed: list[str] = []
    try:
        with transaction(connection):
            rows = connection.execute(
                "SELECT lesson_id FROM lessons WHERE expires_at < ? AND status IN "
                "('Candidate', 'Shadow', 'Active', 'Conflicted')",
                (date.today().isoformat(),),
            ).fetchall()
            for row in rows:
                transition(
                    connection,
                    row["lesson_id"],
                    "Expired",
                    "expiry date reached",
                    now,
                )
                changed.append(row["lesson_id"])
        return {"catalog_path": str(path), "expired_lesson_ids": changed}
    finally:
        connection.close()


def migrate(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(create=False)
    if not path.exists():
        raise CatalogError(f"catalog does not exist: {path}")
    probe = sqlite3.connect(path)
    try:
        before = probe.execute("PRAGMA user_version").fetchone()[0]
    finally:
        probe.close()
    connection = connect(path, writable=True)
    try:
        after = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "catalog_path": str(path),
            "before_schema_version": before,
            "after_schema_version": after,
            "changed": before != after,
        }
    finally:
        connection.close()


def doctor(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(create=False)
    connection = connect(path, writable=False, allow_legacy_read=True)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_issues = [
            list(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "catalog_path": str(path),
            "schema_version": schema_version,
            "supported_schema": schema_version == SCHEMA_VERSION,
            "quick_check": quick_check,
            "foreign_key_issues": foreign_key_issues,
        }
    finally:
        connection.close()


def add_verification_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", action="append", default=[], required=True)
    parser.add_argument("--evidence-id", action="append", default=[], required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--verification-method", required=True)
    parser.add_argument("--verified", action="store_true")
    parser.add_argument("--privacy-reviewed", action="store_true")
    parser.add_argument("--license-reviewed", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("resolve", help="resolve the configured catalog path")

    observe_parser = subparsers.add_parser(
        "observe", help="record one governed observation"
    )
    observe_parser.add_argument("--case-id", required=True)
    observe_parser.add_argument("--claim", required=True)
    observe_parser.add_argument("--scope", required=True)
    observe_parser.add_argument("--version-scope", required=True)
    observe_parser.add_argument("--jurisdiction", required=True)
    observe_parser.add_argument("--expires-at", required=True)
    observe_parser.add_argument("--recheck-trigger", required=True)
    observe_parser.add_argument("--limitations", required=True)
    observe_parser.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    observe_parser.add_argument("--related-lesson-id")
    observe_parser.add_argument("--high-risk-fix", action="store_true")
    add_verification_arguments(observe_parser)

    list_parser = subparsers.add_parser("list", help="list catalog lessons")
    list_parser.add_argument("--status", choices=sorted(STATUSES))
    subparsers.add_parser(
        "load", help="read unexpired Active and Shadow routing candidates"
    )
    subparsers.add_parser("refresh", help="persist deterministic expiry transitions")
    subparsers.add_parser("migrate", help="migrate the catalog to the current schema")
    subparsers.add_parser("doctor", help="check schema and database integrity read-only")

    show_parser = subparsers.add_parser("show", help="show one lesson and audit history")
    show_parser.add_argument("--lesson-id", required=True)

    retire_parser = subparsers.add_parser("retire", help="deprecate or roll back a lesson")
    retire_parser.add_argument("--lesson-id", required=True)
    retire_parser.add_argument(
        "--target", choices=["Deprecated", "Rolled-back"], required=True
    )
    retire_parser.add_argument("--reason", required=True)

    conflict_parser = subparsers.add_parser(
        "resolve-conflict", help="resolve or retain isolation for a recorded conflict"
    )
    conflict_parser.add_argument("--lesson-id", required=True)
    conflict_parser.add_argument("--related-lesson-id", required=True)
    conflict_parser.add_argument(
        "--action",
        choices=["keep-first", "keep-second", "retire-both", "continue-isolation"],
        required=True,
    )
    conflict_parser.add_argument("--reason", required=True)
    add_verification_arguments(conflict_parser)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            result = {"catalog_path": str(database_path(create=False))}
        elif args.command == "observe":
            result = observe(args)
        elif args.command == "list":
            result = list_lessons(args)
        elif args.command == "load":
            result = load_lessons(args)
        elif args.command == "show":
            result = show_lesson(args)
        elif args.command == "retire":
            result = retire(args)
        elif args.command == "resolve-conflict":
            result = resolve_conflict(args)
        elif args.command == "refresh":
            result = refresh(args)
        elif args.command == "migrate":
            result = migrate(args)
        elif args.command == "doctor":
            result = doctor(args)
        else:
            parser.error("unsupported command")
            return 2
    except (CatalogError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
