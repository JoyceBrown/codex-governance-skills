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
from typing import Iterator, Sequence


NAMESPACE = "deliberate-project"
DATABASE_NAME = "experience.sqlite3"
STATUSES = {
    "Candidate",
    "Shadow",
    "Active",
    "Deprecated",
    "Expired",
    "Conflicted",
    "Rolled-back",
}
OUTCOMES = {"candidate", "shadow-benefit", "shadow-regression", "conflict"}
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


def checked_case_id(value: str) -> str:
    value = value.strip()
    if not SAFE_ID.fullmatch(value):
        raise CatalogError("case_id must match [A-Za-z0-9._:-]{1,128}")
    return value


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


def resolve_root(explicit_root: str | None) -> Path:
    configured = (
        explicit_root
        or host_config_root()
        or os.environ.get("AEGOS_SKILLS_EXPERIENCE_ROOT")
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


def database_path(explicit_root: str | None, create: bool) -> Path:
    root = resolve_root(explicit_root)
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


def connect(path: Path, writable: bool, create: bool = False) -> sqlite3.Connection:
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
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if schema_version not in {0, 1}:
            connection.close()
            raise CatalogError(f"unsupported catalog schema version: {schema_version}")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
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
        PRAGMA user_version = 1;
        """
    )


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


def expire_if_needed(connection: sqlite3.Connection, lesson_id: str, now: str) -> None:
    row = connection.execute(
        "SELECT expires_at, status FROM lessons WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    if row and row["expires_at"] < date.today().isoformat() and row["status"] not in {
        "Expired",
        "Deprecated",
        "Rolled-back",
    }:
        transition(connection, lesson_id, "Expired", "expiry date reached", now)


def counts(connection: sqlite3.Connection, lesson_id: str) -> dict[str, int]:
    rows = connection.execute(
        "SELECT outcome, COUNT(DISTINCT case_id) AS count FROM observations "
        "WHERE lesson_id = ? GROUP BY outcome",
        (lesson_id,),
    ).fetchall()
    result = {outcome: 0 for outcome in OUTCOMES}
    result.update({row["outcome"]: row["count"] for row in rows})
    return result


def fetch_lesson(connection: sqlite3.Connection, lesson_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    if row is None:
        raise CatalogError(f"unknown lesson_id: {lesson_id}")
    result = dict(row)
    result["observation_counts"] = counts(connection, lesson_id)
    return result


def observe(args: argparse.Namespace) -> dict[str, object]:
    if not args.privacy_reviewed or not args.license_reviewed:
        raise CatalogError("privacy and licensing review flags are required")
    claim = checked_text(args.claim, "claim", 2000)
    scope = checked_text(args.scope, "scope", 1000)
    version_scope = checked_text(args.version_scope, "version_scope", 300)
    jurisdiction = checked_text(args.jurisdiction, "jurisdiction", 300)
    expires_at = checked_expiry(args.expires_at)
    recheck_trigger = checked_text(args.recheck_trigger, "recheck_trigger", 1000)
    limitations = checked_text(args.limitations, "limitations", 1000)
    case_id = checked_case_id(args.case_id)
    sources = [checked_source(item) for item in args.source]
    if not sources or len(sources) > 20:
        raise CatalogError("provide between 1 and 20 safe source locators")
    if args.outcome == "conflict" and not args.related_lesson_id:
        raise CatalogError("conflict outcome requires related_lesson_id")
    if args.related_lesson_id:
        args.related_lesson_id = checked_lesson_id(
            args.related_lesson_id, "related_lesson_id"
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
    if args.related_lesson_id == lesson_id:
        raise CatalogError("a lesson cannot conflict with itself")
    path = database_path(args.root, create=True)
    now = utc_now()
    connection = connect(path, writable=True, create=True)
    try:
        with transaction(connection):
            existing = connection.execute(
                "SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)
            ).fetchone()
            if existing is None:
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
                    raise CatalogError("lesson identity collision or attempted semantic overwrite")
                before_status = existing["status"]
                connection.execute(
                    "UPDATE lessons SET high_risk_fix = MAX(high_risk_fix, ?), "
                    "updated_at = ? WHERE lesson_id = ?",
                    (int(args.high_risk_fix), now, lesson_id),
                )

            connection.execute(
                "INSERT OR IGNORE INTO observations "
                "(lesson_id, case_id, outcome, source_lineage_json, note, "
                "related_lesson_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    lesson_id,
                    case_id,
                    args.outcome,
                    json.dumps(sources, ensure_ascii=False),
                    "",
                    args.related_lesson_id,
                    now,
                ),
            )

            if args.outcome == "conflict":
                transition(connection, lesson_id, "Conflicted", "unresolved true conflict", now)
                related = connection.execute(
                    "SELECT lesson_id FROM lessons WHERE lesson_id = ?",
                    (args.related_lesson_id,),
                ).fetchone()
                if related is None:
                    raise CatalogError("related conflict lesson does not exist")
                transition(
                    connection,
                    args.related_lesson_id,
                    "Conflicted",
                    f"conflicts with {lesson_id}",
                    now,
                )
            elif args.outcome == "shadow-regression":
                transition(connection, lesson_id, "Rolled-back", "verified shadow regression", now)
            else:
                current = connection.execute(
                    "SELECT status, high_risk_fix FROM lessons WHERE lesson_id = ?",
                    (lesson_id,),
                ).fetchone()
                observation_counts = counts(connection, lesson_id)
                if current["status"] == "Candidate" and (
                    current["high_risk_fix"] or observation_counts["candidate"] >= 2
                ):
                    shadow_reason = (
                        "verified high-risk fix entered Shadow"
                        if current["high_risk_fix"]
                        and observation_counts["candidate"] < 2
                        else "independent recurrence gate satisfied"
                    )
                    transition(
                        connection,
                        lesson_id,
                        "Shadow",
                        shadow_reason,
                        now,
                    )
                current_status = connection.execute(
                    "SELECT status FROM lessons WHERE lesson_id = ?", (lesson_id,)
                ).fetchone()["status"]
                if current_status == "Shadow" and observation_counts["shadow-benefit"] >= 2:
                    transition(
                        connection,
                        lesson_id,
                        "Active",
                        "independent shadow-benefit gate satisfied",
                        now,
                    )
            expire_if_needed(connection, lesson_id, now)
            result = fetch_lesson(connection, lesson_id)
            result["before_status"] = before_status
            result["catalog_path"] = str(path)
            result["recorded_outcome"] = args.outcome
            result["case_id"] = case_id
            return result
    finally:
        connection.close()


def list_lessons(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(args.root, create=False)
    connection = connect(path, writable=False)
    try:
        query = "SELECT lesson_id, claim, scope, status, expires_at, updated_at FROM lessons"
        params: Sequence[str] = ()
        if args.status:
            query += " WHERE status = ?"
            params = (args.status,)
        query += " ORDER BY updated_at DESC, lesson_id"
        lessons = [dict(row) for row in connection.execute(query, params)]
        return {"catalog_path": str(path), "lessons": lessons}
    finally:
        connection.close()


def show_lesson(args: argparse.Namespace) -> dict[str, object]:
    args.lesson_id = checked_lesson_id(args.lesson_id)
    path = database_path(args.root, create=False)
    connection = connect(path, writable=False)
    try:
        result = fetch_lesson(connection, args.lesson_id)
        result["catalog_path"] = str(path)
        result["transitions"] = [
            dict(row)
            for row in connection.execute(
                "SELECT from_status, to_status, reason, created_at FROM transitions "
                "WHERE lesson_id = ? ORDER BY transition_id",
                (args.lesson_id,),
            )
        ]
        return result
    finally:
        connection.close()


def retire(args: argparse.Namespace) -> dict[str, object]:
    args.lesson_id = checked_lesson_id(args.lesson_id)
    if args.target not in {"Deprecated", "Rolled-back"}:
        raise CatalogError("retire target must be Deprecated or Rolled-back")
    reason = checked_text(args.reason, "reason", 1000)
    path = database_path(args.root, create=False)
    connection = connect(path, writable=True)
    now = utc_now()
    try:
        with transaction(connection):
            before, after = transition(connection, args.lesson_id, args.target, reason, now)
            result = fetch_lesson(connection, args.lesson_id)
            result.update(
                {"before_status": before, "after_status": after, "catalog_path": str(path)}
            )
            return result
    finally:
        connection.close()


def refresh(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(args.root, create=False)
    connection = connect(path, writable=True)
    now = utc_now()
    changed: list[str] = []
    try:
        with transaction(connection):
            rows = connection.execute(
                "SELECT lesson_id FROM lessons WHERE expires_at < ? AND status NOT IN "
                "('Expired', 'Deprecated', 'Rolled-back')",
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


def doctor(args: argparse.Namespace) -> dict[str, object]:
    path = database_path(args.root, create=False)
    connection = connect(path, writable=False)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_issues = [
            list(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "catalog_path": str(path),
            "schema_version": schema_version,
            "quick_check": quick_check,
            "foreign_key_issues": foreign_key_issues,
        }
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="explicit configured experience root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("resolve", help="resolve the bounded catalog path")

    observe_parser = subparsers.add_parser("observe", help="record one governed observation")
    observe_parser.add_argument("--case-id", required=True)
    observe_parser.add_argument("--claim", required=True)
    observe_parser.add_argument("--scope", required=True)
    observe_parser.add_argument("--version-scope", required=True)
    observe_parser.add_argument("--jurisdiction", required=True)
    observe_parser.add_argument("--expires-at", required=True)
    observe_parser.add_argument("--recheck-trigger", required=True)
    observe_parser.add_argument("--limitations", required=True)
    observe_parser.add_argument("--source", action="append", default=[], required=True)
    observe_parser.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    observe_parser.add_argument("--related-lesson-id")
    observe_parser.add_argument("--privacy-reviewed", action="store_true")
    observe_parser.add_argument("--license-reviewed", action="store_true")
    observe_parser.add_argument("--high-risk-fix", action="store_true")

    list_parser = subparsers.add_parser("list", help="list catalog lessons")
    list_parser.add_argument("--status", choices=sorted(STATUSES))

    subparsers.add_parser("refresh", help="apply deterministic expiry transitions")
    subparsers.add_parser("doctor", help="check schema and database integrity read-only")

    show_parser = subparsers.add_parser("show", help="show one lesson and its history")
    show_parser.add_argument("--lesson-id", required=True)

    retire_parser = subparsers.add_parser("retire", help="deprecate or roll back a lesson")
    retire_parser.add_argument("--lesson-id", required=True)
    retire_parser.add_argument("--target", choices=["Deprecated", "Rolled-back"], required=True)
    retire_parser.add_argument("--reason", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            result = {"catalog_path": str(database_path(args.root, create=False))}
        elif args.command == "observe":
            result = observe(args)
        elif args.command == "list":
            result = list_lessons(args)
        elif args.command == "show":
            result = show_lesson(args)
        elif args.command == "retire":
            result = retire(args)
        elif args.command == "refresh":
            result = refresh(args)
        elif args.command == "doctor":
            result = doctor(args)
        else:
            parser.error("unsupported command")
            return 2
    except (CatalogError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
