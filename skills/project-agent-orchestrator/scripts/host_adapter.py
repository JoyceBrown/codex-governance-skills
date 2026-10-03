"""Reference adapter for project-agent-orchestrator.

This module is deliberately transport-neutral. It provides the smallest
durable state machine needed by an adapter and is safe to exercise against an
isolated SQLite path. It does not control Codex threads by itself; a host must
bind the callbacks in this module to its real session API.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_VERSION = 2

DEFAULT_COORDINATION_PROFILE: dict[str, Any] = {
    "pattern": "sequential",
    "sop_id": "",
    "sop_step": "",
    "fanout_group_id": "",
    "max_fanout": 0,
    "route_key": "",
    "handoff_target_session_id": "",
    "termination_conditions": ["accepted", "rejected", "blocked", "failed", "cancelled", "unknown"],
}

EVENT_STATUS: dict[str, str] = {
    "task.dispatched": "dispatched",
    "task.started": "running",
    "task.progress": "running",
    "task.waiting": "waiting",
    "task.completed_claim": "completed_claim",
    "task.partial": "partial",
    "task.blocked": "blocked",
    "task.failed": "failed",
    "task.cancelled": "cancelled",
    "task.unknown": "unknown",
    "task.accepted": "accepted",
    "task.rejected": "rejected",
    "task.stale": "stale",
}

RECEIPT_ORIGINS = {
    "worker_reported",
    "parent_recorded",
    "host_observed",
    "adapter_generated",
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "dispatched": {"running", "waiting", "cancelled", "unknown"},
    "running": {
        "running",
        "waiting",
        "completed_claim",
        "partial",
        "blocked",
        "failed",
        "cancelled",
        "unknown",
    },
    "waiting": {"running", "cancelled", "unknown"},
    "completed_claim": {"accepted", "rejected", "unknown"},
    "partial": {"accepted", "rejected", "unknown"},
}

TERMINAL_STATES = {
    "blocked",
    "failed",
    "cancelled",
    "unknown",
    "accepted",
    "rejected",
    "stale",
}

CAPABILITIES = {
    "internal_child": {
        "create_local_child",
        "record_local_child_result",
        "record_capability_check",
        "dependency_barrier_status",
        "archive_session",
    },
    "main_session": {
        "resolve_project",
        "list_role_sessions",
        "resolve_role_session",
        "create_role_session",
        "takeover_role_session",
        "dispatch_task",
        "record_event",
        "wake_session",
        "reconcile_attempt",
        "recover_project",
        "record_capability_check",
        "dependency_barrier_status",
        "archive_session",
    },
    "commander": {
        "resolve_project",
        "list_role_sessions",
        "resolve_role_session",
        "create_role_session",
        "takeover_role_session",
        "dispatch_task",
        "record_event",
        "wake_session",
        "reconcile_attempt",
        "recover_project",
        "record_capability_check",
        "dependency_barrier_status",
        "archive_session",
    },
}

HANDOFF_CAPABILITIES = {
    "main_session": {
        "resolve_project",
        "resolve_role_session",
        "create_role_session",
        "record_handoff",
        "fence_session",
        "reconcile_attempt",
        "send_checkpoint",
        "wake_session",
        "recover_project",
    },
    "commander": {
        "resolve_project",
        "create_role_session",
        "record_handoff",
        "fence_session",
        "reconcile_attempt",
        "send_checkpoint",
        "wake_session",
        "recover_project",
    },
}

# Dispatch does not require cleanup of a temporary session. Cleanup is a
# separate lifecycle operation and must run its own preflight before it is
# attempted, so a missing archive API cannot be hidden until the end of a
# task.
DISPATCH_CAPABILITIES = {
    target_kind: capabilities - {"archive_session"}
    for target_kind, capabilities in CAPABILITIES.items()
    if target_kind in {"internal_child", "main_session", "commander"}
}


def rotation_recommendation(
    *,
    context_fraction: float | None = None,
    compaction_count: int = 0,
    context_window_exceeded: bool = False,
    instruction_drift: bool = False,
    plan_drift: bool = False,
    accepted_state_contradiction: bool = False,
    input_cost_rising: bool = False,
) -> dict[str, Any]:
    """Classify whether a role session should be kept, prepared, or rotated.

    The function is deliberately conservative: a missing usage metric is not
    converted into a guessed percentage, and a first compaction only prepares
    a checkpoint.  Callers still execute the resulting action at a safe
    side-effect boundary.
    """
    if context_fraction is not None:
        if not isinstance(context_fraction, (int, float)) or isinstance(context_fraction, bool):
            raise ValueError("context_fraction must be numeric or None")
        if not 0 <= float(context_fraction) <= 1:
            raise ValueError("context_fraction must be between 0 and 1")
    if not isinstance(compaction_count, int) or compaction_count < 0:
        raise ValueError("compaction_count must be a non-negative integer")

    reasons: list[str] = []
    rotate_now = False
    prepare = False
    if context_window_exceeded:
        rotate_now = True
        reasons.append("context_window_exceeded")
    if compaction_count >= 2:
        rotate_now = True
        reasons.append("second_compaction_or_more")
    elif compaction_count == 1:
        prepare = True
        reasons.append("first_compaction")
    if instruction_drift:
        rotate_now = True
        reasons.append("verified_instruction_drift")
    if plan_drift:
        rotate_now = True
        reasons.append("verified_plan_drift")
    if accepted_state_contradiction:
        rotate_now = True
        reasons.append("accepted_state_contradiction")
    if context_fraction is not None and float(context_fraction) >= 0.80:
        prepare = True
        reasons.append("context_usage_at_or_above_80_percent")
    if input_cost_rising:
        prepare = True
        reasons.append("input_cost_rising")

    decision = "rotate_now" if rotate_now else "prepare_rotation" if prepare else "continue"
    return {
        "decision": decision,
        "action": decision,
        "reasons": reasons,
        "safe_boundary_required": True,
        "context_fraction": context_fraction,
        "compaction_count": compaction_count,
    }

PACKET_FIELDS = {
    "schema_version",
    "project_id",
    "plan_id",
    "plan_revision",
    "snapshot_id",
    "snapshot_hash",
    "capability_check_id",
    "permission_boundary",
    "session_resolution",
    "candidate_session_ids",
    "role_epoch",
    "previous_owner_session_id",
    "handoff_receipt_id",
    "acceptance_mode",
    "acceptance_authority_session_id",
    "acceptance_authority_permission_boundary",
    "acceptance_scope_id",
    "task_id",
    "attempt_id",
    "root_session_id",
    "parent_session_id",
    "target_kind",
    "target_session_id",
    "role_id",
    "commander_epoch",
    "ancestor_session_ids",
    "dispatch_depth",
    "dependency_task_ids",
    "join_policy",
    "objective",
    "allowed_scope",
    "excluded_scope",
    "acceptance_criteria",
    "acceptance_policy_version",
    "inputs_and_evidence_refs",
    "output_contract",
    "side_effects_policy",
    "lease_id",
    "commander_lease_id",
    "lease_expires_at",
    "cancel_epoch",
    "max_attempts",
    "budget_and_deadline",
    "callback_to",
    "task_contract_hash",
    "idempotency_key",
}

EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "event_type",
    "status",
    "project_id",
    "plan_id",
    "plan_revision",
    "snapshot_id",
    "snapshot_hash",
    "capability_check_id",
    "permission_boundary",
    "task_id",
    "attempt_id",
    "task_contract_hash",
    "root_session_id",
    "session_id",
    "target_session_id",
    "parent_session_id",
    "callback_to",
    "commander_epoch",
    "session_resolution",
    "candidate_session_ids",
    "role_id",
    "role_epoch",
    "previous_owner_session_id",
    "handoff_receipt_id",
    "acceptance_mode",
    "acceptance_authority_session_id",
    "acceptance_authority_permission_boundary",
    "acceptance_scope_id",
    "validation_receipt_id",
    "accepted_for_event_id",
    "validated_by_session_id",
    "validation_evidence_refs",
    "rejection_reasons",
    "emitted_by_session_id",
    "receipt_origin",
    "observed_by",
    "sequence",
    "cancel_epoch",
    "idempotency_key",
}


class AdapterError(ValueError):
    """A rejected task, event, or lifecycle transition."""


def _now() -> int:
    return int(time.time() * 1000)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _with_default_coordination_profile(value: dict[str, Any]) -> dict[str, Any]:
    if "coordination_profile" in value:
        return value
    enriched = dict(value)
    enriched["coordination_profile"] = {
        **DEFAULT_COORDINATION_PROFILE,
        "termination_conditions": list(DEFAULT_COORDINATION_PROFILE["termination_conditions"]),
    }
    return enriched


def _with_default_receipt_provenance(value: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(value)
    if "receipt_origin" not in enriched:
        event_type = enriched.get("event_type")
        if event_type in {"task.dispatched", "task.stale"}:
            origin = "adapter_generated"
        elif event_type in {"task.accepted", "task.rejected", "task.cancelled", "task.unknown"}:
            origin = "parent_recorded"
        else:
            origin = "worker_reported"
        enriched["receipt_origin"] = origin
    enriched.setdefault("observed_by", "")
    return enriched


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _expired(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def _contract_digest(packet: dict[str, Any]) -> str:
    """Return the canonical digest for an immutable task packet."""
    material = {
        key: value
        for key, value in packet.items()
        if key not in {"task_contract_hash", "capability_check_id"}
    }
    return "sha256:" + hashlib.sha256(_json(material).encode("utf-8")).hexdigest()


class ContractPacket(dict[str, Any]):
    """Test/helper packet that keeps its contract digest in sync with edits."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._refresh_contract_hash()

    def _refresh_contract_hash(self) -> None:
        dict.__setitem__(self, "task_contract_hash", _contract_digest(self))

    def __setitem__(self, key: str, value: Any) -> None:
        dict.__setitem__(self, key, value)
        if key != "task_contract_hash":
            self._refresh_contract_hash()

    def update(self, *args: Any, **kwargs: Any) -> None:
        dict.update(self, *args, **kwargs)
        self._refresh_contract_hash()

    def pop(self, key: str, *args: Any) -> Any:
        value = dict.pop(self, key, *args)
        if key != "task_contract_hash":
            self._refresh_contract_hash()
        return value


class HostAdapter:
    """A small durable state machine for isolated adapter integration tests."""

    def __init__(
        self,
        store_path: str | Path,
        *,
        max_dispatch_depth: int = 32,
        session_authenticator: Callable[[dict[str, Any], str], bool] | None = None,
    ):
        if max_dispatch_depth < 1:
            raise ValueError("max_dispatch_depth must be positive")
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.store_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.max_dispatch_depth = max_dispatch_depth
        self.session_authenticator = session_authenticator
        self._init_schema()

    def close(self) -> None:
        self.db.close()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS capability_checks (
                check_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                target_kind TEXT NOT NULL,
                operation TEXT NOT NULL DEFAULT 'dispatch',
                transport TEXT NOT NULL DEFAULT 'state_machine',
                required_json TEXT NOT NULL,
                available_json TEXT NOT NULL,
                missing_json TEXT NOT NULL,
                canonical_target_id TEXT,
                checked_by TEXT NOT NULL,
                checked_at INTEGER NOT NULL,
                result TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                plan_revision TEXT NOT NULL DEFAULT '',
                snapshot_id TEXT NOT NULL,
                commander_session_id TEXT NOT NULL,
                commander_epoch TEXT NOT NULL,
                commander_lease_id TEXT NOT NULL,
                lease_expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                role_id TEXT,
                parent_session_id TEXT,
                target_kind TEXT NOT NULL,
                plan_id TEXT,
                snapshot_id TEXT,
                permission_boundary TEXT NOT NULL DEFAULT '',
                lifecycle TEXT NOT NULL DEFAULT 'active',
                health_status TEXT NOT NULL DEFAULT 'unknown',
                owner_session_id TEXT,
                lease_id TEXT,
                lease_expires_at TEXT,
                role_epoch INTEGER NOT NULL DEFAULT 1,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS session_receipts (
                receipt_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                role_id TEXT NOT NULL,
                session_id TEXT,
                resolution TEXT NOT NULL,
                candidate_session_ids_json TEXT NOT NULL,
                requesting_owner_session_id TEXT,
                previous_owner_session_id TEXT,
                role_epoch INTEGER,
                handoff_receipt_id TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS handoff_receipts (
                handoff_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                role_id TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL,
                state TEXT NOT NULL,
                old_session_id TEXT NOT NULL,
                new_session_id TEXT NOT NULL,
                old_epoch TEXT NOT NULL,
                new_epoch TEXT NOT NULL,
                old_lease_id TEXT,
                new_lease_id TEXT,
                plan_id TEXT NOT NULL,
                plan_revision TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                permission_boundary TEXT NOT NULL,
                old_status_evidence_ref TEXT NOT NULL DEFAULT '',
                checkpoint_ref TEXT NOT NULL DEFAULT '',
                successor_ack_ref TEXT NOT NULL DEFAULT '',
                in_flight_attempt_ids_json TEXT NOT NULL DEFAULT '[]',
                reconciliation_refs_json TEXT NOT NULL DEFAULT '[]',
                authorized_actor TEXT NOT NULL,
                rotation_reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                committed_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT '',
                attempt_id TEXT NOT NULL UNIQUE,
                dispatch_idempotency_key TEXT NOT NULL UNIQUE,
                packet_json TEXT NOT NULL,
                state TEXT NOT NULL,
                last_source_sequence INTEGER,
                cancel_epoch TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                packet_json TEXT NOT NULL,
                state TEXT NOT NULL,
                last_source_sequence INTEGER,
                cancel_epoch TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(task_id, attempt_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                source_sequence INTEGER,
                receipt_sequence INTEGER NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                stale_reason TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS child_edges (
                parent_session_id TEXT NOT NULL,
                child_session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wake_deliveries (
                receipt_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                delivery_attempt INTEGER NOT NULL DEFAULT 1,
                acknowledged_at INTEGER,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dispatch_deliveries (
                delivery_receipt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                target_session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                host_receipt_id TEXT NOT NULL DEFAULT '',
                delivery_attempt INTEGER NOT NULL DEFAULT 1,
                acknowledged_at INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(task_id, attempt_id)
            );
            CREATE TABLE IF NOT EXISTS acceptance_receipts (
                validation_receipt_id TEXT PRIMARY KEY,
                acceptance_scope_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                validator_session_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(acceptance_scope_id, task_id, attempt_id)
            );
            CREATE TABLE IF NOT EXISTS dependency_barriers (
                task_id TEXT PRIMARY KEY,
                dependency_task_ids_json TEXT NOT NULL,
                join_policy TEXT NOT NULL,
                state TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS receipt_counters (
                stream_name TEXT PRIMARY KEY,
                next_sequence INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_task_idx ON events(task_id, attempt_id);
            CREATE INDEX IF NOT EXISTS events_idempotency_idx ON events(idempotency_key);
            """
        )
        self.db.execute(
            "INSERT OR IGNORE INTO receipt_counters(stream_name, next_sequence) VALUES ('events', 1)"
        )
        max_receipt = self.db.execute("SELECT COALESCE(MAX(receipt_sequence), 0) FROM events").fetchone()[0]
        self.db.execute(
            "UPDATE receipt_counters SET next_sequence = ? WHERE stream_name='events' AND next_sequence <= ?",
            (int(max_receipt) + 1, int(max_receipt) + 1),
        )
        # Keep the reference adapter usable with a store created by an older
        # revision. SQLite has no portable IF NOT EXISTS form for columns.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        for name, definition in {
            "plan_id": "TEXT",
            "plan_revision": "TEXT NOT NULL DEFAULT ''",
            "snapshot_id": "TEXT",
            "permission_boundary": "TEXT NOT NULL DEFAULT ''",
            "lifecycle": "TEXT NOT NULL DEFAULT 'active'",
            "health_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "owner_session_id": "TEXT",
            "lease_id": "TEXT",
            "lease_expires_at": "TEXT",
            "role_epoch": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in columns:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        task_columns = {row[1] for row in self.db.execute("PRAGMA table_info(tasks)")}
        if "project_id" not in task_columns:
            self.db.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT NOT NULL DEFAULT ''")
        for task_row in self.db.execute("SELECT task_id, packet_json, project_id FROM tasks WHERE project_id='' ").fetchall():
            try:
                task_project_id = json.loads(task_row["packet_json"]).get("project_id")
            except (TypeError, ValueError, json.JSONDecodeError):
                task_project_id = None
            if task_project_id:
                self.db.execute(
                    "UPDATE tasks SET project_id=? WHERE task_id=?",
                    (task_project_id, task_row["task_id"]),
                )
        project_columns = {row[1] for row in self.db.execute("PRAGMA table_info(projects)")}
        if "plan_revision" not in project_columns:
            self.db.execute("ALTER TABLE projects ADD COLUMN plan_revision TEXT NOT NULL DEFAULT ''")
        capability_columns = {row[1] for row in self.db.execute("PRAGMA table_info(capability_checks)")}
        if "operation" not in capability_columns:
            self.db.execute("ALTER TABLE capability_checks ADD COLUMN operation TEXT NOT NULL DEFAULT 'dispatch'")
        if "transport" not in capability_columns:
            self.db.execute("ALTER TABLE capability_checks ADD COLUMN transport TEXT NOT NULL DEFAULT 'state_machine'")
        self.db.commit()

    def _next_receipt_sequence(self) -> int:
        # The UPDATE obtains SQLite's write lock and avoids MAX+1 races across
        # adapter instances sharing the same store.
        self.db.execute(
            "UPDATE receipt_counters SET next_sequence = next_sequence + 1 WHERE stream_name='events'"
        )
        row = self.db.execute(
            "SELECT next_sequence - 1 FROM receipt_counters WHERE stream_name='events'"
        ).fetchone()
        return int(row[0])

    def _session_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "project_id": row["project_id"],
            "role_id": row["role_id"],
            "parent_session_id": row["parent_session_id"],
            "target_kind": row["target_kind"],
            "plan_id": row["plan_id"],
            "plan_revision": row["plan_revision"],
            "snapshot_id": row["snapshot_id"],
            "permission_boundary": row["permission_boundary"],
            "lifecycle": row["lifecycle"],
            "health_status": row["health_status"],
            "owner_session_id": row["owner_session_id"],
            "lease_id": row["lease_id"],
            "lease_expires_at": row["lease_expires_at"],
            "role_epoch": row["role_epoch"],
            "archived": bool(row["archived"]),
        }

    def _record_session_receipt(
        self,
        *,
        project_id: str,
        role_id: str,
        session_id: str | None,
        resolution: str,
        candidate_session_ids: list[str],
        requesting_owner_session_id: str | None,
        previous_owner_session_id: str | None = None,
        role_epoch: int | None = None,
        handoff_receipt_id: str | None = None,
    ) -> str:
        receipt_id = _new_id("res")
        self.db.execute(
            """INSERT INTO session_receipts
            (receipt_id, project_id, role_id, session_id, resolution,
             candidate_session_ids_json, requesting_owner_session_id,
             previous_owner_session_id, role_epoch, handoff_receipt_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt_id,
                project_id,
                role_id,
                session_id,
                resolution,
                _json(candidate_session_ids),
                requesting_owner_session_id,
                previous_owner_session_id,
                role_epoch,
                handoff_receipt_id,
                _now(),
            ),
        )
        return receipt_id

    def resolve_project(
        self,
        *,
        project_id: str,
        plan_id: str,
        snapshot_id: str,
        plan_revision: str = "",
        commander_session_id: str,
        commander_epoch: str,
        commander_lease_id: str,
        lease_expires_at: str | None = None,
        commit: bool = True,
        fresh_start: bool = False,
        archive_callback: Callable[[str], bool] | None = None,
        authorized_actor: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the project commander lease and plan boundary.

        ``fresh_start`` is an explicit clean-restart path.  It retires the
        previous commander only after all tasks are terminal and the host has
        confirmed its thread cleanup.  It never sends a checkpoint and never
        waits for an old session to acknowledge anything.
        """
        if not plan_revision:
            raise AdapterError("plan_revision_required")
        row = self.db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row:
            if row["commander_session_id"] != commander_session_id and fresh_start:
                active_tasks = self.db.execute(
                    "SELECT task_id, state FROM tasks WHERE project_id=? AND state NOT IN (?, ?, ?, ?, ?, ?, ?)",
                    (project_id, "blocked", "failed", "cancelled", "unknown", "accepted", "rejected", "stale"),
                ).fetchall()
                if active_tasks:
                    return {
                        "result": "fresh_start_requires_reconciliation",
                        "project_id": project_id,
                        "active_tasks": [dict(item) for item in active_tasks],
                    }
                old_session_id = row["commander_session_id"]
                old_session = self.db.execute(
                    "SELECT * FROM sessions WHERE session_id=? AND project_id=?",
                    (old_session_id, project_id),
                ).fetchone()
                if old_session and not old_session["archived"]:
                    if archive_callback is None:
                        return {
                            "result": "fresh_start_cleanup_required",
                            "project_id": project_id,
                            "old_commander_session_id": old_session_id,
                            "missing": ["archive_session"],
                        }
                    descendants = self._retire_project_descendants(
                        project_id,
                        old_session_id,
                        archive_callback,
                        actor_session_id=authorized_actor or old_session_id,
                    )
                    if descendants.get("result") != "retired":
                        return {
                            "result": "fresh_start_cleanup_" + str(descendants.get("result", "unknown")),
                            "project_id": project_id,
                            "old_commander_session_id": old_session_id,
                            "cleanup": descendants,
                        }
                    cleanup = self.archive_session(
                        old_session_id,
                        archive_callback,
                        actor_session_id=authorized_actor or old_session_id,
                    )
                    if cleanup.get("result") != "archived":
                        return {
                            "result": "fresh_start_cleanup_" + str(cleanup.get("result", "unknown")),
                            "project_id": project_id,
                            "old_commander_session_id": old_session_id,
                            "cleanup": cleanup,
                        }
                now = _now()
                self.db.execute("SAVEPOINT pao_fresh_start")
                try:
                    self.db.execute(
                        """UPDATE projects SET plan_id=?, plan_revision=?, snapshot_id=?,
                           commander_session_id=?, commander_epoch=?, commander_lease_id=?,
                           lease_expires_at=?, active=1, updated_at=? WHERE project_id=?""",
                        (
                            plan_id, plan_revision, snapshot_id, commander_session_id,
                            commander_epoch, commander_lease_id, lease_expires_at, now, project_id,
                        ),
                    )
                    self._ensure_session(
                        session_id=commander_session_id,
                        project_id=project_id,
                        role_id="",
                        parent_session_id=None,
                        target_kind="commander",
                        plan_id=plan_id,
                        snapshot_id=snapshot_id,
                        permission_boundary="",
                        owner_session_id=commander_session_id,
                        lease_id=commander_lease_id,
                        lease_expires_at=lease_expires_at,
                        role_epoch=1,
                    )
                    if commit:
                        self.db.commit()
                    else:
                        self.db.execute("RELEASE SAVEPOINT pao_fresh_start")
                except Exception:
                    try:
                        self.db.execute("ROLLBACK TO SAVEPOINT pao_fresh_start")
                        self.db.execute("RELEASE SAVEPOINT pao_fresh_start")
                    finally:
                        self.db.rollback()
                    raise
                return {
                    "result": "fresh_started",
                    "project_id": project_id,
                    "commander_session_id": commander_session_id,
                    "commander_epoch": commander_epoch,
                    "old_commander_session_id": old_session_id,
                }
            if not row["active"] or row["commander_session_id"] != commander_session_id:
                raise AdapterError("commander_conflict")
            if _expired(row["lease_expires_at"]):
                raise AdapterError("lease_expired")
            if row["plan_id"] != plan_id or row["plan_revision"] != plan_revision or row["snapshot_id"] != snapshot_id:
                raise AdapterError("plan_drift")
            if row["commander_epoch"] != commander_epoch or row["commander_lease_id"] != commander_lease_id:
                raise AdapterError("stale_commander_epoch")
            return {"result": "resolved", "project_id": project_id, "commander_session_id": commander_session_id, "commander_epoch": commander_epoch}
        now = _now()
        self.db.execute(
            """INSERT INTO projects
            (project_id, plan_id, plan_revision, snapshot_id, commander_session_id, commander_epoch,
             commander_lease_id, lease_expires_at, active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (project_id, plan_id, plan_revision, snapshot_id, commander_session_id, commander_epoch, commander_lease_id, lease_expires_at, now),
        )
        self._ensure_session(
            session_id=commander_session_id,
            project_id=project_id,
            role_id="",
            parent_session_id=None,
            target_kind="commander",
            plan_id=plan_id,
            snapshot_id=snapshot_id,
            permission_boundary="",
            owner_session_id=commander_session_id,
            lease_id=commander_lease_id,
            lease_expires_at=lease_expires_at,
            role_epoch=1,
        )
        if commit:
            self.db.commit()
        return {"result": "resolved", "project_id": project_id, "commander_session_id": commander_session_id, "commander_epoch": commander_epoch}

    def _retire_project_descendants(
        self,
        project_id: str,
        commander_session_id: str,
        archive_callback: Callable[[str], bool],
        *,
        actor_session_id: str,
    ) -> dict[str, Any]:
        """Close old role/child rows bottom-up during an explicit fresh start."""
        remaining = {
            str(row["session_id"])
            for row in self.db.execute(
                "SELECT session_id FROM sessions WHERE project_id=? AND session_id<>? AND archived=0",
                (project_id, commander_session_id),
            ).fetchall()
        }
        while remaining:
            progressed = False
            for session_id in list(remaining):
                result = self.archive_session(
                    session_id,
                    archive_callback,
                    actor_session_id=actor_session_id,
                )
                if result.get("result") == "archived":
                    remaining.remove(session_id)
                    progressed = True
                elif result.get("result") not in {"children_active"}:
                    return {
                        "result": result.get("result", "unknown"),
                        "session_id": session_id,
                        "detail": result,
                    }
            if not progressed:
                return {"result": "children_active", "remaining_session_ids": sorted(remaining)}
        return {"result": "retired"}

    def recover_project(self, *, project_id: str, commander_epoch: str) -> dict[str, Any]:
        """Return durable project/task cursors for a commander after interruption."""
        row = self.db.execute(
            "SELECT * FROM projects WHERE project_id=? AND commander_epoch=? AND active=1",
            (project_id, commander_epoch),
        ).fetchone()
        if not row:
            return {"result": "target_unresolved", "project_id": project_id}
        tasks = self.db.execute(
            "SELECT task_id, attempt_id, state, updated_at FROM tasks WHERE project_id=? ORDER BY updated_at, task_id",
            (project_id,),
        ).fetchall()
        return {
            "result": "recovered",
            "project_id": project_id,
            "plan_id": row["plan_id"],
            "snapshot_id": row["snapshot_id"],
            "commander_session_id": row["commander_session_id"],
            "commander_epoch": row["commander_epoch"],
            "tasks": [dict(item) for item in tasks],
        }

    def _ensure_session(
        self,
        *,
        session_id: str,
        project_id: str,
        role_id: str | None,
        parent_session_id: str | None,
        target_kind: str,
        plan_id: str,
        snapshot_id: str,
        permission_boundary: str,
        owner_session_id: str | None,
        lease_id: str | None,
        lease_expires_at: str | None = None,
        role_epoch: int = 1,
    ) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row:
            if row["archived"] or row["lifecycle"] not in {"active", "suspended"}:
                # Canonical host thread IDs are single-use.  Rebinding a
                # closed row would make a project point at a session that can
                # never receive work again.
                raise AdapterError("session_id_reused")
            if row["project_id"] != project_id or row["target_kind"] != target_kind:
                raise AdapterError("target_unresolved")
            if row["role_id"] != (role_id or None):
                raise AdapterError("role_binding_mismatch")
            if (row["parent_session_id"] or None) != (parent_session_id or None):
                raise AdapterError("parent_binding_mismatch")
            if row["plan_id"] not in {None, plan_id} or row["snapshot_id"] not in {None, snapshot_id}:
                raise AdapterError("plan_drift")
            if row["permission_boundary"] != (permission_boundary or ""):
                raise AdapterError("permission_boundary_mismatch")
            if row["lease_expires_at"] and _expired(row["lease_expires_at"]):
                raise AdapterError("lease_expired")
            if int(row["role_epoch"]) != int(role_epoch):
                raise AdapterError("stale_role_epoch")
            return row
        now = _now()
        self.db.execute(
            """INSERT INTO sessions
            (session_id, project_id, role_id, parent_session_id, target_kind,
             plan_id, snapshot_id, permission_boundary, lifecycle, health_status,
             owner_session_id, lease_id, lease_expires_at, role_epoch, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 'unknown', ?, ?, ?, ?, 0, ?, ?)""",
            (
                session_id,
                project_id,
                role_id,
                parent_session_id,
                target_kind,
                plan_id,
                snapshot_id,
                permission_boundary or "",
                owner_session_id,
                lease_id,
                lease_expires_at,
                int(role_epoch),
                now,
                now,
            ),
        )
        return self.db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()

    def register_session(
        self,
        *,
        session_id: str,
        project_id: str,
        role_id: str | None,
        parent_session_id: str | None,
        target_kind: str,
        plan_id: str,
        snapshot_id: str,
        permission_boundary: str = "",
        owner_session_id: str | None = None,
        lease_id: str | None = None,
        lease_expires_at: str | None = None,
        role_epoch: int = 1,
    ) -> dict[str, Any]:
        effective_owner = owner_session_id or parent_session_id
        if effective_owner:
            owner = self.db.execute(
                "SELECT session_id FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
                (effective_owner, project_id),
            ).fetchone()
            if not owner and not (target_kind == "commander" and effective_owner == session_id):
                raise AdapterError("owner_unresolved")
        row = self._ensure_session(
            session_id=session_id,
            project_id=project_id,
            role_id=role_id,
            parent_session_id=parent_session_id,
            target_kind=target_kind,
            plan_id=plan_id,
            snapshot_id=snapshot_id,
            permission_boundary=permission_boundary,
            owner_session_id=effective_owner,
            lease_id=lease_id,
            lease_expires_at=lease_expires_at,
            role_epoch=role_epoch,
        )
        if owner_session_id and row["owner_session_id"] != owner_session_id:
            raise AdapterError("owner_conflict")
        if lease_id and row["lease_id"] != lease_id:
            raise AdapterError("lease_conflict")
        self.db.commit()
        return self._session_dict(row)

    def _session_chain(self, session_id: str) -> list[str]:
        chain: list[str] = []
        current: str | None = session_id
        while current:
            if current in chain:
                raise AdapterError("cycle_detected")
            row = self.db.execute(
                "SELECT session_id, parent_session_id FROM sessions WHERE session_id=?", (current,)
            ).fetchone()
            if not row:
                raise AdapterError("target_unresolved")
            chain.append(row["session_id"])
            current = row["parent_session_id"]
        return chain

    def _authenticate_emitter(
        self,
        packet: dict[str, Any],
        event: dict[str, Any],
        emitter: str,
        *,
        allow_superseded_epoch: bool = False,
    ) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (emitter,)).fetchone()
        if not row or row["project_id"] != packet["project_id"] or row["archived"] or row["lifecycle"] not in {"active", "suspended"}:
            raise AdapterError("source_authentication")
        if row["lease_expires_at"] and _expired(row["lease_expires_at"]):
            raise AdapterError("lease_expired")
        if packet.get("lease_expires_at") and _expired(packet["lease_expires_at"]):
            raise AdapterError("lease_expired")
        expected_boundary = packet["permission_boundary"] if emitter == packet["target_session_id"] else packet["acceptance_authority_permission_boundary"]
        if row["permission_boundary"] != expected_boundary:
            raise AdapterError("permission_boundary_mismatch")
        if emitter == packet["target_session_id"]:
            if row["role_id"] != (packet.get("role_id") or None) or (
                not allow_superseded_epoch and int(row["role_epoch"]) != int(packet["role_epoch"])
            ):
                raise AdapterError("source_authentication")
        if self.session_authenticator and not self.session_authenticator(dict(row), emitter):
            raise AdapterError("source_authentication")
        return row

    def wake_session(
        self,
        session_id: str,
        receipt_id: str,
        wake_callback: Callable[[str, str], bool] | None = None,
    ) -> dict[str, Any]:
        """Deliver a durable receipt wake exactly once when the host supports it."""
        existing = self.db.execute(
            "SELECT * FROM wake_deliveries WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        if existing:
            if existing["session_id"] != session_id:
                return {"result": "target_unresolved", "receipt_id": receipt_id, "session_id": session_id}
            if existing["status"] == "delivered":
                return {"result": "duplicate", "receipt_id": receipt_id, "status": existing["status"]}
            if wake_callback is None:
                return {"result": "unknown", "receipt_id": receipt_id, "status": existing["status"], "retryable": True}
            try:
                delivered = bool(wake_callback(session_id, receipt_id))
            except Exception:
                delivered = False
            status = "delivered" if delivered else "unknown"
            self.db.execute(
                """UPDATE wake_deliveries SET status=?, delivery_attempt=delivery_attempt+1,
                acknowledged_at=? WHERE receipt_id=?""",
                (status, _now() if delivered else None, receipt_id),
            )
            self.db.commit()
            return {"result": status, "receipt_id": receipt_id, "session_id": session_id, "retryable": not delivered}
        session = self.db.execute(
            "SELECT session_id FROM sessions WHERE session_id=? AND archived=0", (session_id,)
        ).fetchone()
        if not session:
            return {"result": "target_unresolved", "session_id": session_id}
        if wake_callback is None:
            return {"result": "capability_gap", "missing": ["wake_session"]}
        try:
            delivered = bool(wake_callback(session_id, receipt_id))
        except Exception:
            delivered = False
        status = "delivered" if delivered else "unknown"
        self.db.execute(
            """INSERT INTO wake_deliveries
            (receipt_id, session_id, status, delivery_attempt, acknowledged_at, created_at)
            VALUES (?, ?, ?, 1, ?, ?)""",
            (receipt_id, session_id, status, _now() if delivered else None, _now()),
        )
        self.db.commit()
        return {"result": "delivered" if delivered else "unknown", "receipt_id": receipt_id, "session_id": session_id}

    def reconcile_attempt(self, *, project_id: str, task_id: str, attempt_id: str) -> dict[str, Any]:
        """Return the durable attempt state before a retry or recovery decision."""
        task = self.db.execute(
            "SELECT * FROM tasks WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
        ).fetchone()
        if not task:
            task = self.db.execute(
                "SELECT * FROM attempts WHERE task_id=? AND attempt_id=?", (task_id, attempt_id)
            ).fetchone()
        if not task:
            return {"result": "target_unresolved", "task_id": task_id, "attempt_id": attempt_id}
        packet = _with_default_coordination_profile(json.loads(task["packet_json"]))
        if packet["project_id"] != project_id:
            return {"result": "target_unresolved", "task_id": task_id, "attempt_id": attempt_id}
        latest = self.db.execute(
            """SELECT event_id, event_type, status, receipt_sequence, stale_reason
            FROM events WHERE task_id=? AND attempt_id=? ORDER BY receipt_sequence DESC LIMIT 1""",
            (task_id, attempt_id),
        ).fetchone()
        delivery = self.db.execute(
            """SELECT delivery_receipt_id, target_session_id, status,
            host_receipt_id, delivery_attempt, acknowledged_at
            FROM dispatch_deliveries WHERE task_id=? AND attempt_id=?""",
            (task_id, attempt_id),
        ).fetchone()
        return {
            "result": "reconciled",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "state": task["state"],
            "cancel_epoch": task["cancel_epoch"],
            "latest_receipt": dict(latest) if latest else None,
            "dispatch_delivery": dict(delivery) if delivery else None,
        }

    def create_local_child(self, parent_session_id: str, task_packet: dict[str, Any]) -> dict[str, Any]:
        """Bind a local child to its parent and use the same durable dispatch path."""
        if task_packet.get("target_kind") != "internal_child" or task_packet.get("parent_session_id") != parent_session_id:
            raise AdapterError("target_unresolved")
        return self.dispatch(task_packet, task_packet["capability_check_id"])

    def record_local_child_result(self, parent_session_id: str, event_envelope: dict[str, Any]) -> dict[str, Any]:
        """Record a local child callback only when it returns to its immediate parent."""
        if event_envelope.get("parent_session_id") != parent_session_id:
            raise AdapterError("callback_target_mismatch")
        return self.record_event(event_envelope)

    def list_role_sessions(
        self,
        *,
        project_id: str,
        role_id: str,
        plan_id: str | None = None,
        snapshot_id: str | None = None,
        permission_boundary: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """List compatible durable role sessions without selecting one."""
        if not role_id:
            raise AdapterError("role_id_required")
        clauses = [
            "project_id = ?",
            "role_id = ?",
            "target_kind = 'main_session'",
            "lifecycle IN ('active', 'suspended')",
            "health_status NOT IN ('lost', 'unhealthy', 'handoff_pending', 'parent_handoff_pending', 'commander_handoff_pending')",
        ]
        args: list[Any] = [project_id, role_id]
        if not include_archived:
            clauses.append("archived = 0")
        if plan_id is not None:
            clauses.append("(plan_id = ? OR plan_id IS NULL)")
            args.append(plan_id)
        if snapshot_id is not None:
            clauses.append("(snapshot_id = ? OR snapshot_id IS NULL)")
            args.append(snapshot_id)
        if permission_boundary is not None:
            clauses.append("permission_boundary = ?")
            args.append(permission_boundary)
        rows = self.db.execute(
            f"SELECT * FROM sessions WHERE {' AND '.join(clauses)} ORDER BY created_at, session_id",
            args,
        ).fetchall()
        return [self._session_dict(row) for row in rows]

    def create_role_session(
        self,
        *,
        project_id: str,
        role_id: str,
        parent_session_id: str,
        plan_id: str,
        snapshot_id: str,
        owner_session_id: str | None = None,
        permission_boundary: str | None = None,
        session_id: str | None = None,
        candidate_session_ids: list[str] | None = None,
        lease_expires_at: str | None = None,
        initial_lifecycle: str = "active",
        initial_health_status: str | None = None,
    ) -> dict[str, Any]:
        """Create a durable role session and a resolution receipt."""
        if not role_id or not parent_session_id:
            raise AdapterError("role_id_and_parent_required")
        if initial_lifecycle not in {"active", "suspended"}:
            raise AdapterError("initial_lifecycle_invalid")
        if initial_lifecycle == "suspended" and initial_health_status not in {
            "handoff_pending", "parent_handoff_pending", "commander_handoff_pending"
        }:
            raise AdapterError("initial_health_status_invalid")
        parent = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND target_kind IN ('commander','main_session') AND archived=0 AND lifecycle IN ('active','suspended')",
            (parent_session_id, project_id),
        ).fetchone()
        if not parent:
            raise AdapterError("parent_unresolved")
        effective_owner = owner_session_id or parent_session_id
        owner = self.db.execute(
            "SELECT session_id FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
            (effective_owner, project_id),
        ).fetchone()
        if not owner:
            raise AdapterError("owner_unresolved")
        if lease_expires_at and _expired(lease_expires_at):
            raise AdapterError("lease_expired")
        if permission_boundary is not None and permission_boundary != parent["permission_boundary"]:
            raise AdapterError("permission_boundary_escalation")
        session_id = session_id or _new_id("role")
        now = _now()
        lease_id = _new_id("lease") if initial_lifecycle == "active" else None
        health_status = initial_health_status or "unknown"
        try:
            self.db.execute(
                """INSERT INTO sessions
                (session_id, project_id, role_id, parent_session_id, target_kind,
                 plan_id, snapshot_id, permission_boundary, lifecycle, health_status,
                 owner_session_id, lease_id, lease_expires_at, role_epoch, archived, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'main_session', ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
                (
                    session_id,
                    project_id,
                    role_id,
                    parent_session_id,
                    plan_id,
                    snapshot_id,
                    permission_boundary or "",
                    initial_lifecycle,
                    health_status,
                    effective_owner,
                    lease_id,
                    lease_expires_at,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AdapterError("session_id_conflict") from exc
        receipt_id = self._record_session_receipt(
            project_id=project_id,
            role_id=role_id,
            session_id=session_id,
            resolution="new",
            candidate_session_ids=candidate_session_ids or [],
            requesting_owner_session_id=effective_owner,
            role_epoch=1,
        )
        self.db.commit()
        result = self._session_dict(self.db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone())
        result.update(
            {
                "result": "resolved",
                "session_resolution": "new",
                "candidate_session_ids": candidate_session_ids or [],
                "previous_owner_session_id": "",
                "handoff_receipt_id": "",
                "resolution_receipt_id": receipt_id,
            }
        )
        return result

    def retire_role_session(
        self,
        session_id: str,
        archive_callback: Callable[[str], bool] | None = None,
        *,
        actor_session_id: str | None = None,
        reason: str = "expired",
    ) -> dict[str, Any]:
        """Retire an expired role without invoking the handoff protocol.

        This path is deliberately separate from takeover/session replacement:
        it requires no checkpoint ACK because the old role is no longer being
        continued.  Open tasks and child edges still stop retirement so the
        caller cannot discard live work by accident.
        """
        row = self.db.execute(
            "SELECT target_kind FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row or row["target_kind"] != "main_session":
            return {"result": "target_unresolved", "session_id": session_id}
        active_tasks = self.db.execute(
            """SELECT task_id, state FROM tasks
               WHERE json_extract(packet_json, '$.target_session_id')=?
               AND state NOT IN (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, "blocked", "failed", "cancelled", "unknown", "accepted", "rejected", "stale"),
        ).fetchall()
        if active_tasks:
            return {
                "result": "active_tasks",
                "session_id": session_id,
                "tasks": [dict(item) for item in active_tasks],
            }
        archived = self.archive_session(
            session_id,
            archive_callback,
            actor_session_id=actor_session_id,
        )
        if archived.get("result") != "archived":
            return archived
        self.db.execute(
            "UPDATE sessions SET health_status=?, updated_at=? WHERE session_id=?",
            (reason or "expired", _now(), session_id),
        )
        self.db.commit()
        return {
            "result": "retired",
            "session_id": session_id,
            "reason": reason or "expired",
        }

    def takeover_role_session(
        self,
        *,
        project_id: str,
        role_id: str,
        candidate_session_id: str,
        new_owner_session_id: str,
        expected_role_epoch: int | None = None,
        expected_lease_id: str | None = None,
        authorized: bool = False,
    ) -> dict[str, Any]:
        """Transfer a role lease only after explicit authorization and CAS checks."""
        if not authorized:
            return {"result": "authorization_required", "session_id": candidate_session_id}
        if not expected_lease_id:
            return {"result": "lease_check_required", "session_id": candidate_session_id}
        new_owner = self.db.execute(
            "SELECT session_id, project_id, permission_boundary, archived, lifecycle FROM sessions WHERE session_id=?",
            (new_owner_session_id,),
        ).fetchone()
        if not new_owner or new_owner["project_id"] != project_id or new_owner["archived"] or new_owner["lifecycle"] not in {"active", "suspended"}:
            return {"result": "owner_unresolved", "session_id": candidate_session_id}
        row = self.db.execute(
            """SELECT * FROM sessions WHERE session_id=? AND project_id=? AND role_id=?
            AND target_kind='main_session' AND archived=0
            AND lifecycle IN ('active', 'suspended')
            AND health_status NOT IN ('lost', 'unhealthy')""",
            (candidate_session_id, project_id, role_id),
        ).fetchone()
        if not row:
            return {"result": "target_unresolved", "session_id": candidate_session_id}
        if expected_role_epoch is not None and int(row["role_epoch"]) != int(expected_role_epoch):
            return {"result": "lease_conflict", "session_id": candidate_session_id, "role_epoch": row["role_epoch"]}
        if expected_lease_id is not None and row["lease_id"] != expected_lease_id:
            return {"result": "lease_conflict", "session_id": candidate_session_id, "role_epoch": row["role_epoch"]}
        if new_owner["permission_boundary"] != row["permission_boundary"]:
            return {"result": "permission_boundary_mismatch", "session_id": candidate_session_id}
        previous_owner = row["owner_session_id"]
        next_epoch = int(row["role_epoch"]) + 1
        lease_id = _new_id("lease")
        handoff_receipt_id = _new_id("handoff")
        now = _now()
        update_cursor = self.db.execute(
            """UPDATE sessions SET owner_session_id=?, lease_id=?, role_epoch=?, updated_at=?
            WHERE session_id=? AND role_epoch=?""",
            (new_owner_session_id, lease_id, next_epoch, now, candidate_session_id, row["role_epoch"]),
        )
        if update_cursor.rowcount != 1:
            self.db.rollback()
            return {"result": "lease_conflict", "session_id": candidate_session_id}
        resolution_receipt_id = self._record_session_receipt(
            project_id=project_id,
            role_id=role_id,
            session_id=candidate_session_id,
            resolution="takeover",
            candidate_session_ids=[candidate_session_id],
            requesting_owner_session_id=new_owner_session_id,
            previous_owner_session_id=previous_owner,
            role_epoch=next_epoch,
            handoff_receipt_id=handoff_receipt_id,
        )
        self.db.commit()
        result = self._session_dict(self.db.execute("SELECT * FROM sessions WHERE session_id=?", (candidate_session_id,)).fetchone())
        result.update({"result": "resolved", "session_resolution": "takeover", "previous_owner_session_id": previous_owner or "", "handoff_receipt_id": handoff_receipt_id, "resolution_receipt_id": resolution_receipt_id})
        return result

    def prepare_handoff(
        self,
        *,
        project_id: str,
        mode: str,
        old_session_id: str,
        new_session_id: str,
        plan_id: str,
        plan_revision: str,
        snapshot_id: str,
        capability_check_id: str,
        authorized_actor: str,
        checkpoint_ref: str = "",
        old_status_evidence_ref: str = "",
        rotation_reason: str = "",
        expected_old_epoch: int | str | None = None,
        expected_old_lease_id: str | None = None,
    ) -> dict[str, Any]:
        """Freeze an old identity and persist a two-phase replacement receipt.

        The successor must already be registered by the host.  This method is
        the durable prepare phase; ``commit_handoff`` requires a host
        checkpoint acknowledgement before activating the successor.
        """
        if mode not in {"session_replace", "commander_replace"}:
            raise AdapterError("handoff_mode_invalid")
        old = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=?",
            (old_session_id, project_id),
        ).fetchone()
        new = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=?",
            (new_session_id, project_id),
        ).fetchone()
        if not old or not new or old["archived"] or new["archived"]:
            return {"result": "target_unresolved", "old_session_id": old_session_id, "new_session_id": new_session_id}
        if old["plan_id"] not in {None, plan_id} or old["snapshot_id"] not in {None, snapshot_id}:
            raise AdapterError("plan_drift")
        if new["plan_id"] not in {None, plan_id} or new["snapshot_id"] not in {None, snapshot_id}:
            raise AdapterError("plan_drift")
        if old["permission_boundary"] != new["permission_boundary"]:
            raise AdapterError("permission_boundary_mismatch")
        project = None
        if mode == "session_replace":
            if old["target_kind"] != "main_session" or new["target_kind"] != "main_session":
                raise AdapterError("handoff_target_kind_invalid")
            if old["role_id"] != new["role_id"]:
                raise AdapterError("role_binding_mismatch")
            if old["parent_session_id"] != new["parent_session_id"]:
                raise AdapterError("parent_binding_mismatch")
        else:
            if old["target_kind"] != "commander" or new["target_kind"] != "commander":
                raise AdapterError("handoff_target_kind_invalid")
            project = self.db.execute(
                "SELECT * FROM projects WHERE project_id=? AND active=1", (project_id,)
            ).fetchone()
            if not project or project["commander_session_id"] != old_session_id:
                raise AdapterError("commander_conflict")
            # The project row owns the commander lease and epoch.  The
            # session role_epoch is an integer local generation and may not
            # match the host's opaque commander epoch after a restart.
        actor = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
            (authorized_actor, project_id),
        ).fetchone()
        if not actor or (authorized_actor != old["owner_session_id"] and actor["target_kind"] != "commander"):
            return {"result": "source_authentication", "old_session_id": old_session_id}
        expected_epoch = project["commander_epoch"] if mode == "commander_replace" else old["role_epoch"]
        expected_lease = project["commander_lease_id"] if mode == "commander_replace" else old["lease_id"]
        check = self.db.execute(
            "SELECT * FROM capability_checks WHERE check_id=? AND operation='handoff'",
            (capability_check_id,),
        ).fetchone()
        if not check or check["result"] != "ready" or check["project_id"] != project_id or check["plan_id"] != plan_id or check["snapshot_id"] != snapshot_id or check["canonical_target_id"] != old_session_id:
            raise AdapterError("capability_gap")
        existing = self.db.execute(
            "SELECT * FROM handoff_receipts WHERE old_session_id=? AND new_session_id=? AND state IN ('prepared','committed')",
            (old_session_id, new_session_id),
        ).fetchone()
        if existing:
            return {"result": existing["state"], "handoff_id": existing["handoff_id"], "old_session_id": old_session_id, "new_session_id": new_session_id}
        if mode == "commander_replace" and old["lease_id"] != project["commander_lease_id"]:
            return {"result": "lease_conflict", "old_session_id": old_session_id}
        if expected_old_epoch is not None and str(expected_epoch) != str(expected_old_epoch):
            return {"result": "lease_conflict", "old_session_id": old_session_id}
        if expected_old_lease_id is not None and expected_lease != expected_old_lease_id:
            return {"result": "lease_conflict", "old_session_id": old_session_id}
        old_epoch = str(expected_epoch)
        new_epoch = str(int(old["role_epoch"]) + 1) if mode == "session_replace" else _new_id("epoch")
        new_lease = _new_id("lease")
        in_flight = self.db.execute(
            "SELECT task_id, attempt_id, packet_json, state, cancel_epoch FROM tasks WHERE project_id=? AND json_extract(packet_json, '$.target_session_id')=? AND state NOT IN (%s)" % ",".join("?" for _ in TERMINAL_STATES),
            [project_id, old_session_id, *sorted(TERMINAL_STATES)],
        ).fetchall()
        now = _now()
        self.db.execute("SAVEPOINT pao_handoff_prepare")
        try:
            handoff_id = _new_id("handoff")
            self.db.execute(
                """INSERT INTO handoff_receipts
                (handoff_id, project_id, role_id, mode, state, old_session_id,
                 new_session_id, old_epoch, new_epoch, old_lease_id, new_lease_id,
                 plan_id, plan_revision, snapshot_id, permission_boundary,
                 old_status_evidence_ref, checkpoint_ref, in_flight_attempt_ids_json,
                 authorized_actor, rotation_reason, created_at)
                VALUES (?, ?, ?, ?, 'prepared', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    handoff_id, project_id, old["role_id"] or "", mode,
                    old_session_id, new_session_id, old_epoch, new_epoch,
                    old["lease_id"], new_lease, plan_id, plan_revision,
                    snapshot_id, old["permission_boundary"], old_status_evidence_ref,
                    checkpoint_ref, _json([row["attempt_id"] for row in in_flight]),
                    authorized_actor, rotation_reason, now,
                ),
            )
            updated_old = self.db.execute(
                "UPDATE sessions SET lifecycle='suspended', health_status='handoff_pending', lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE session_id=? AND role_epoch=? AND lease_id=? AND archived=0",
                (now, old_session_id, old["role_epoch"], expected_lease),
            )
            if updated_old.rowcount != 1:
                self.db.execute("ROLLBACK TO SAVEPOINT pao_handoff_prepare")
                self.db.execute("RELEASE SAVEPOINT pao_handoff_prepare")
                self.db.rollback()
                return {"result": "lease_conflict", "old_session_id": old_session_id}
            if mode == "commander_replace":
                self.db.execute(
                    "UPDATE sessions SET lifecycle='suspended', health_status='commander_handoff_pending', lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE project_id=? AND session_id NOT IN (?, ?) AND archived=0",
                    (now, project_id, old_session_id, new_session_id),
                )
            else:
                self.db.execute(
                    "UPDATE sessions SET lifecycle='suspended', health_status='parent_handoff_pending', lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE parent_session_id=? AND archived=0",
                    (now, old_session_id),
                )
            # Child ownership cannot silently remain attached to an identity
            # that is being retired.  Mark the edge stale so the old session
            # can be archived; a successor must explicitly rebind or replace
            # each suspended child before it receives more work.
            self.db.execute(
                "UPDATE child_edges SET status='stale' WHERE parent_session_id=? AND status='open'",
                (old_session_id,),
            )
            for row in in_flight:
                packet = _with_default_coordination_profile(json.loads(row["packet_json"]))
                event_id = _new_id("evt")
                payload = event_template(packet, "task.unknown", 1)
                payload.update({"event_id": event_id, "sequence": None, "emitted_by_session_id": authorized_actor, "receipt_origin": "adapter_generated", "observed_by": "handoff", "unknown_reason": "session_replaced", "handoff_id": handoff_id, "idempotency_key": f"{packet['idempotency_key']}/unknown/{handoff_id}"})
                self._insert_event(event_id=event_id, task_id=row["task_id"], attempt_id=row["attempt_id"], event_type="task.unknown", status="unknown", source_sequence=None, idempotency_key=payload["idempotency_key"], payload=payload)
                self.db.execute("UPDATE tasks SET state='unknown', cancel_epoch=?, updated_at=? WHERE task_id=? AND attempt_id=?", (f"{row['cancel_epoch']}:handoff", now, row["task_id"], row["attempt_id"]))
                self.db.execute("UPDATE attempts SET state='unknown', cancel_epoch=?, updated_at=? WHERE task_id=? AND attempt_id=?", (f"{row['cancel_epoch']}:handoff", now, row["task_id"], row["attempt_id"]))
            self.db.execute("RELEASE SAVEPOINT pao_handoff_prepare")
            self.db.commit()
        except Exception:
            self.db.execute("ROLLBACK TO SAVEPOINT pao_handoff_prepare")
            self.db.execute("RELEASE SAVEPOINT pao_handoff_prepare")
            self.db.rollback()
            raise
        return {"result": "prepared", "handoff_id": handoff_id, "old_session_id": old_session_id, "new_session_id": new_session_id, "old_epoch": old_epoch, "new_epoch": new_epoch, "new_lease_id": new_lease, "in_flight_attempt_ids": [row["attempt_id"] for row in in_flight]}

    def commit_handoff(
        self,
        handoff_id: str,
        checkpoint_callback: Callable[[str, str], Any] | None = None,
        *,
        successor_ack_ref: str | None = None,
        wake_callback: Callable[[str, str], bool] | None = None,
    ) -> dict[str, Any]:
        """Activate a prepared successor only after host checkpoint acknowledgement."""
        handoff = self.db.execute("SELECT * FROM handoff_receipts WHERE handoff_id=?", (handoff_id,)).fetchone()
        if not handoff:
            return {"result": "target_unresolved", "handoff_id": handoff_id}
        if handoff["state"] == "committed":
            return {"result": "duplicate", "handoff_id": handoff_id, "new_session_id": handoff["new_session_id"]}
        if handoff["state"] != "prepared":
            return {"result": handoff["state"], "handoff_id": handoff_id}
        if checkpoint_callback is None:
            return {"result": "capability_gap", "missing": ["send_checkpoint"], "handoff_id": handoff_id}
        try:
            acknowledgement = checkpoint_callback(handoff["new_session_id"], handoff_id)
        except Exception:
            acknowledgement = None
        if isinstance(acknowledgement, dict):
            ack_status = acknowledgement.get("status")
            ack_ref = acknowledgement.get("host_receipt_id") or acknowledgement.get("ack_ref")
            ack_target = acknowledgement.get("target_session_id")
            if ack_status != "acknowledged" or ack_target != handoff["new_session_id"] or not ack_ref:
                self.db.execute("UPDATE handoff_receipts SET state='unknown' WHERE handoff_id=? AND state='prepared'", (handoff_id,))
                self.db.commit()
                return {"result": "unknown", "handoff_id": handoff_id}
            successor_ack_ref = str(ack_ref)
        elif not successor_ack_ref:
            self.db.execute("UPDATE handoff_receipts SET state='unknown' WHERE handoff_id=? AND state='prepared'", (handoff_id,))
            self.db.commit()
            return {"result": "unknown", "handoff_id": handoff_id}
        now = _now()
        self.db.execute("BEGIN")
        try:
            current = self.db.execute("SELECT * FROM handoff_receipts WHERE handoff_id=? AND state='prepared'", (handoff_id,)).fetchone()
            old = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (handoff["old_session_id"],)).fetchone()
            new = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (handoff["new_session_id"],)).fetchone()
            if not current or not old or not new or old["lease_id"] is not None:
                self.db.rollback()
                return {"result": "lease_conflict", "handoff_id": handoff_id}
            updated = self.db.execute(
                "UPDATE sessions SET lifecycle='active', health_status='unknown', owner_session_id=?, lease_id=?, lease_expires_at=NULL, role_epoch=?, updated_at=? WHERE session_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
                (new["session_id"], handoff["new_lease_id"], int(handoff["new_epoch"]) if handoff["mode"] == "session_replace" else new["role_epoch"], now, new["session_id"]),
            )
            if updated.rowcount != 1:
                self.db.rollback()
                return {"result": "lease_conflict", "handoff_id": handoff_id}
            if handoff["mode"] == "commander_replace":
                project_update = self.db.execute(
                    "UPDATE projects SET commander_session_id=?, commander_epoch=?, commander_lease_id=?, updated_at=? WHERE project_id=? AND commander_session_id=? AND commander_epoch=?",
                    (handoff["new_session_id"], handoff["new_epoch"], handoff["new_lease_id"], now, handoff["project_id"], handoff["old_session_id"], handoff["old_epoch"]),
                )
                if project_update.rowcount != 1:
                    self.db.rollback()
                    return {"result": "lease_conflict", "handoff_id": handoff_id}
            self.db.execute("UPDATE handoff_receipts SET state='committed', successor_ack_ref=?, committed_at=? WHERE handoff_id=? AND state='prepared'", (successor_ack_ref, now, handoff_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        wake = self.wake_session(handoff["new_session_id"], handoff_id, wake_callback) if wake_callback else {"result": "capability_gap", "missing": ["wake_session"]}
        return {"result": "committed", "handoff_id": handoff_id, "new_session_id": handoff["new_session_id"], "new_epoch": handoff["new_epoch"], "wake": wake}

    def retry_handoff(self, handoff_id: str, *, authorized_actor: str) -> dict[str, Any]:
        """Reopen an uncertain checkpoint for one authenticated retry.

        The old lease remains fenced.  Retrying only changes the durable
        handoff state from ``unknown`` back to ``prepared``; it does not
        reactivate either session or reopen any task attempt.
        """
        handoff = self.db.execute(
            "SELECT * FROM handoff_receipts WHERE handoff_id=?", (handoff_id,)
        ).fetchone()
        if not handoff:
            return {"result": "target_unresolved", "handoff_id": handoff_id}
        if handoff["state"] == "prepared":
            return {"result": "prepared", "handoff_id": handoff_id}
        if handoff["state"] == "committed":
            return {"result": "duplicate", "handoff_id": handoff_id}
        if handoff["state"] != "unknown":
            return {"result": handoff["state"], "handoff_id": handoff_id}
        actor = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
            (authorized_actor, handoff["project_id"]),
        ).fetchone()
        if not actor or (authorized_actor != handoff["authorized_actor"] and actor["target_kind"] != "commander"):
            return {"result": "source_authentication", "handoff_id": handoff_id}
        old = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0",
            (handoff["old_session_id"], handoff["project_id"]),
        ).fetchone()
        new = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0",
            (handoff["new_session_id"], handoff["project_id"]),
        ).fetchone()
        if not old or not new or old["lease_id"] is not None:
            return {"result": "lease_conflict", "handoff_id": handoff_id}
        self.db.execute(
            "UPDATE handoff_receipts SET state='prepared' WHERE handoff_id=? AND state='unknown'",
            (handoff_id,),
        )
        self.db.commit()
        return {"result": "prepared", "handoff_id": handoff_id, "retryable": True}

    def resolve_role_session(
        self,
        *,
        project_id: str,
        role_id: str,
        parent_session_id: str,
        plan_id: str,
        snapshot_id: str,
        decision: str | None = None,
        candidate_session_id: str | None = None,
        owner_session_id: str | None = None,
        authorized: bool = False,
        expected_role_epoch: int | None = None,
        expected_lease_id: str | None = None,
        permission_boundary: str | None = None,
    ) -> dict[str, Any]:
        """Resolve reuse/takeover/new without silently duplicating a role."""
        candidates = self.list_role_sessions(
            project_id=project_id,
            role_id=role_id,
            plan_id=plan_id,
            snapshot_id=snapshot_id,
            permission_boundary=permission_boundary,
        )
        candidate_ids = [item["session_id"] for item in candidates]
        if candidates and decision is None:
            receipt_id = self._record_session_receipt(
                project_id=project_id,
                role_id=role_id,
                session_id=None,
                resolution="pending",
                candidate_session_ids=candidate_ids,
                requesting_owner_session_id=owner_session_id or parent_session_id,
            )
            self.db.commit()
            return {
                "result": "session_resolution_pending",
                "candidate_session_ids": candidate_ids,
                "role_id": role_id,
                "resolution_receipt_id": receipt_id,
            }
        decision = decision or "new"
        if decision not in {"reuse", "takeover", "new"}:
            raise AdapterError("invalid_session_resolution")
        if decision == "new":
            return self.create_role_session(
                project_id=project_id,
                role_id=role_id,
                parent_session_id=parent_session_id,
                plan_id=plan_id,
                snapshot_id=snapshot_id,
                owner_session_id=owner_session_id or parent_session_id,
                permission_boundary=permission_boundary or "",
                candidate_session_ids=candidate_ids,
            )
        if candidate_session_id not in candidate_ids:
            raise AdapterError("candidate_session_unresolved")
        candidate = next(item for item in candidates if item["session_id"] == candidate_session_id)
        if decision == "reuse":
            receipt_id = self._record_session_receipt(
                project_id=project_id,
                role_id=role_id,
                session_id=candidate_session_id,
                resolution="reuse",
                candidate_session_ids=candidate_ids,
                requesting_owner_session_id=owner_session_id or parent_session_id,
                role_epoch=int(candidate["role_epoch"]),
            )
            self.db.commit()
            candidate.update({"result": "resolved", "session_resolution": "reuse", "resolution_receipt_id": receipt_id, "candidate_session_ids": candidate_ids, "previous_owner_session_id": "", "handoff_receipt_id": ""})
            return candidate
        if not expected_lease_id:
            return {"result": "lease_check_required", "session_id": candidate_session_id, "candidate_session_ids": candidate_ids}
        result = self.takeover_role_session(
            project_id=project_id,
            role_id=role_id,
            candidate_session_id=candidate_session_id,
            new_owner_session_id=owner_session_id or parent_session_id,
            expected_role_epoch=expected_role_epoch if expected_role_epoch is not None else int(candidate["role_epoch"]),
            expected_lease_id=expected_lease_id,
            authorized=authorized,
        )
        result["candidate_session_ids"] = candidate_ids
        return result

    # Compatibility alias for hosts that used the pre-resolution name.
    def resolve_or_create_session(self, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_role_session(**kwargs)

    def record_capability_check(
        self,
        *,
        project_id: str,
        plan_id: str,
        snapshot_id: str,
        target_kind: str,
        canonical_target_id: str | None,
        required_capabilities: Iterable[str],
        available_capabilities: Iterable[str],
        checked_by: str,
        operation: str = "dispatch",
        transport: str = "state_machine",
    ) -> dict[str, Any]:
        if operation not in {"dispatch", "cleanup", "handoff"}:
            raise AdapterError("operation_invalid")
        if transport not in {"state_machine", "host"}:
            raise AdapterError("transport_invalid")
        required = set(required_capabilities)
        available = set(available_capabilities)
        missing = sorted(required - available)
        result = "target_unresolved" if not canonical_target_id else ("capability_gap" if missing else "ready")
        check_id = _new_id("cap")
        checked_at = _now()
        self.db.execute(
            """INSERT INTO capability_checks
            (check_id, project_id, plan_id, snapshot_id, target_kind, operation, transport,
             required_json, available_json, missing_json, canonical_target_id,
             checked_by, checked_at, result)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                check_id,
                project_id,
                plan_id,
                snapshot_id,
                target_kind,
                operation,
                transport,
                _json(sorted(required)),
                _json(sorted(available)),
                _json(missing),
                canonical_target_id,
                checked_by,
                checked_at,
                result,
            ),
        )
        self.db.commit()
        return {
            "capability_check_id": check_id,
            "project_id": project_id,
            "plan_id": plan_id,
            "snapshot_id": snapshot_id,
            "target_kind": target_kind,
            "operation": operation,
            "transport": transport,
            "required_capabilities": sorted(required),
            "available_capabilities": sorted(available),
            "missing_capabilities": missing,
            "canonical_target_id": canonical_target_id,
            "checked_by": checked_by,
            "checked_at": checked_at,
            "result": result,
        }

    def preflight(
        self,
        *,
        project_id: str,
        plan_id: str,
        snapshot_id: str,
        target_kind: str,
        canonical_target_id: str | None,
        available_capabilities: Iterable[str],
        checked_by: str,
        operation: str = "dispatch",
        transport: str = "state_machine",
    ) -> dict[str, Any]:
        if target_kind not in CAPABILITIES:
            raise AdapterError(f"unknown target_kind: {target_kind}")
        if operation not in {"dispatch", "cleanup", "handoff"}:
            raise AdapterError("operation_invalid")
        if transport not in {"state_machine", "host"}:
            raise AdapterError("transport_invalid")
        if operation == "dispatch":
            required = DISPATCH_CAPABILITIES[target_kind]
        elif operation == "cleanup":
            required = {"archive_session"}
        else:
            if target_kind not in HANDOFF_CAPABILITIES:
                raise AdapterError("handoff_target_kind_invalid")
            required = HANDOFF_CAPABILITIES[target_kind]
        if operation == "dispatch" and transport == "host":
            required = set(required) | {"send_task"}
        if operation == "handoff" and transport == "host":
            required = set(required) | {"create_session", "send_checkpoint"}
        return self.record_capability_check(
            project_id=project_id,
            plan_id=plan_id,
            snapshot_id=snapshot_id,
            target_kind=target_kind,
            canonical_target_id=canonical_target_id,
            required_capabilities=required,
            available_capabilities=available_capabilities,
            checked_by=checked_by,
            operation=operation,
            transport=transport,
        )

    def _validate_dependency_graph(self, packet: dict[str, Any]) -> None:
        dependencies = packet["dependency_task_ids"]
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies) or len(dependencies) != len(set(dependencies)):
            raise AdapterError("dependency_ids_invalid")
        if packet["task_id"] in dependencies:
            raise AdapterError("cycle_detected")
        join_policy = packet["join_policy"]
        if isinstance(join_policy, str):
            valid_policy = join_policy in {"none", "all", "any"}
            policy_mode = join_policy
        elif isinstance(join_policy, dict):
            policy_mode = join_policy.get("mode")
            valid_policy = policy_mode == "bounded_partial" and isinstance(join_policy.get("min_accepted"), int) and join_policy["min_accepted"] >= 1
        else:
            valid_policy = False
            policy_mode = None
        if not valid_policy:
            raise AdapterError("join_policy_invalid")
        if dependencies and policy_mode == "none":
            raise AdapterError("join_policy_invalid")
        if not dependencies and policy_mode not in {"none", "all"}:
            raise AdapterError("join_policy_invalid")
        if policy_mode == "bounded_partial" and join_policy["min_accepted"] > len(dependencies):
            raise AdapterError("join_policy_invalid")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(dependency_id: str) -> None:
            if dependency_id == packet["task_id"] or dependency_id in visiting:
                raise AdapterError("cycle_detected")
            if dependency_id in visited:
                return
            row = self.db.execute("SELECT packet_json FROM tasks WHERE task_id=?", (dependency_id,)).fetchone()
            if not row:
                raise AdapterError("dependency_unresolved")
            visiting.add(dependency_id)
            dependency_packet = json.loads(row["packet_json"])
            for field in ("project_id", "plan_id", "plan_revision", "snapshot_id", "snapshot_hash", "commander_epoch"):
                if dependency_packet.get(field) != packet.get(field):
                    raise AdapterError("dependency_context_mismatch")
            for parent_id in dependency_packet.get("dependency_task_ids", []):
                visit(parent_id)
            visiting.remove(dependency_id)
            visited.add(dependency_id)

        for dependency_id in dependencies:
            visit(dependency_id)

    def _dependency_barrier_state(self, dependency_ids: list[str], join_policy: Any, context: dict[str, Any] | None = None) -> str:
        if not dependency_ids:
            return "ready"
        query = "SELECT task_id, state, packet_json FROM tasks WHERE task_id IN (%s)" % ",".join("?" for _ in dependency_ids)
        rows = self.db.execute(query, dependency_ids).fetchall()
        if context:
            for row in rows:
                dep_packet = json.loads(row["packet_json"])
                if any(dep_packet.get(field) != context.get(field) for field in ("project_id", "plan_id", "plan_revision", "snapshot_id", "snapshot_hash", "commander_epoch")):
                    return "blocked"
        states = {row["task_id"]: row["state"] for row in rows}
        if len(states) != len(set(dependency_ids)):
            return "waiting"
        accepted = sum(state == "accepted" for state in states.values())
        terminal = all(state in TERMINAL_STATES for state in states.values())
        if isinstance(join_policy, dict) and join_policy.get("mode") == "bounded_partial":
            if accepted >= int(join_policy["min_accepted"]):
                return "ready"
            return "blocked" if terminal else "waiting"
        if join_policy == "any":
            if accepted:
                return "ready"
            return "blocked" if terminal else "waiting"
        if all(state == "accepted" for state in states.values()):
            return "ready"
        return "blocked" if terminal else "waiting"

    def _validate_coordination_profile(self, profile: Any) -> None:
        if not isinstance(profile, dict):
            raise AdapterError("coordination_profile_invalid")
        pattern = profile.get("pattern")
        if pattern not in {"sequential", "sop", "fan_out", "conditional", "handoff"}:
            raise AdapterError("coordination_pattern_invalid")
        allowed_terminal_events = {
            "accepted", "rejected", "blocked", "failed", "cancelled", "unknown"
        }
        termination = profile.get("termination_conditions")
        if (
            not isinstance(termination, list)
            or not termination
            or any(item not in allowed_terminal_events for item in termination)
        ):
            raise AdapterError("termination_conditions_invalid")
        if pattern == "sop" and not profile.get("sop_id"):
            raise AdapterError("sop_id_required")
        if pattern == "fan_out":
            if not profile.get("fanout_group_id"):
                raise AdapterError("fanout_group_required")
            if not isinstance(profile.get("max_fanout"), int) or profile["max_fanout"] < 1:
                raise AdapterError("fanout_limit_invalid")
        if pattern == "conditional" and not profile.get("route_key"):
            raise AdapterError("route_key_required")
        if pattern == "handoff" and not profile.get("handoff_target_session_id"):
            raise AdapterError("handoff_target_required")

    def dependency_barrier_status(self, task_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM dependency_barriers WHERE task_id=?", (task_id,)
        ).fetchone()
        if not row:
            return {"result": "target_unresolved", "task_id": task_id}
        dependency_ids = json.loads(row["dependency_task_ids_json"])
        join_policy = json.loads(row["join_policy"])
        task = self.db.execute("SELECT packet_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        context = json.loads(task["packet_json"]) if task else None
        state = self._dependency_barrier_state(dependency_ids, join_policy, context)
        self.db.execute(
            "UPDATE dependency_barriers SET state=?, updated_at=? WHERE task_id=?",
            (state, _now(), task_id),
        )
        self.db.commit()
        return {"result": "reconciled", "task_id": task_id, "state": state, "dependency_task_ids": dependency_ids, "join_policy": join_policy}

    def _refresh_dependency_barriers(self) -> None:
        rows = self.db.execute("SELECT task_id, dependency_task_ids_json, join_policy FROM dependency_barriers").fetchall()
        for row in rows:
            dependencies = json.loads(row["dependency_task_ids_json"])
            policy = json.loads(row["join_policy"])
            task = self.db.execute("SELECT packet_json FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
            context = json.loads(task["packet_json"]) if task else None
            state = self._dependency_barrier_state(dependencies, policy, context)
            self.db.execute(
                "UPDATE dependency_barriers SET state=?, updated_at=? WHERE task_id=?",
                (state, _now(), row["task_id"]),
            )

    def _validate_dispatch_graph(self, packet: dict[str, Any]) -> None:
        if not isinstance(packet["ancestor_session_ids"], list):
            raise AdapterError("ancestor_chain_invalid")
        if not isinstance(packet["dispatch_depth"], int) or packet["dispatch_depth"] < 1:
            raise AdapterError("dispatch_depth_invalid")
        if packet["dispatch_depth"] > self.max_dispatch_depth:
            raise AdapterError("dispatch_depth_exceeded")
        if packet["parent_session_id"]:
            parent_row = self.db.execute(
                "SELECT parent_session_id FROM sessions WHERE session_id=?", (packet["parent_session_id"],)
            ).fetchone()
            if not parent_row and packet["parent_session_id"] == packet["root_session_id"]:
                chain = [packet["parent_session_id"]]
            else:
                chain = self._session_chain(packet["parent_session_id"])
            expected_ancestors = chain[1:]
            expected_root = chain[-1]
            expected_depth = len(chain)
            if packet["ancestor_session_ids"] != expected_ancestors:
                raise AdapterError("ancestor_chain_mismatch")
            if packet["root_session_id"] != expected_root:
                raise AdapterError("root_session_mismatch")
            if packet["dispatch_depth"] != expected_depth:
                raise AdapterError("dispatch_depth_mismatch")
        elif packet["target_kind"] != "commander":
            raise AdapterError("parent_required")

    def dispatch(self, packet: dict[str, Any], capability_check_id: str) -> dict[str, Any]:
        """Atomically validate and persist one immutable task attempt."""
        self.db.execute("SAVEPOINT pao_dispatch")
        try:
            result = self._dispatch_unprotected(packet, capability_check_id)
        except Exception:
            self.db.execute("ROLLBACK TO SAVEPOINT pao_dispatch")
            self.db.execute("RELEASE SAVEPOINT pao_dispatch")
            self.db.rollback()
            raise
        self.db.execute("RELEASE SAVEPOINT pao_dispatch")
        self.db.commit()
        return result

    def _dispatch_unprotected(self, packet: dict[str, Any], capability_check_id: str) -> dict[str, Any]:
        missing = sorted(PACKET_FIELDS - packet.keys())
        if missing:
            raise AdapterError(f"packet_missing:{','.join(missing)}")
        packet = _with_default_coordination_profile(packet)
        if packet["schema_version"] != SCHEMA_VERSION:
            raise AdapterError("schema_unsupported")
        if packet["target_kind"] not in CAPABILITIES:
            raise AdapterError("target_unresolved")
        if packet["session_resolution"] not in {"reuse", "takeover", "new"}:
            raise AdapterError("invalid_session_resolution")
        if not isinstance(packet["candidate_session_ids"], list):
            raise AdapterError("candidate_session_ids_invalid")
        if packet["target_kind"] == "main_session" and not packet["role_id"]:
            raise AdapterError("role_id_required")
        if packet["acceptance_mode"] not in {"commander_gate", "independent_validator"}:
            raise AdapterError("acceptance_mode_invalid")
        self._validate_coordination_profile(packet["coordination_profile"])
        if packet.get("task_contract_hash") != _contract_digest(packet):
            raise AdapterError("task_contract_hash_mismatch")
        profile = packet["coordination_profile"]
        if profile["pattern"] == "handoff":
            handoff_target = profile["handoff_target_session_id"]
            if handoff_target == packet["target_session_id"]:
                raise AdapterError("handoff_target_invalid")
            handoff_row = self.db.execute(
                "SELECT project_id, archived, lifecycle FROM sessions WHERE session_id=?",
                (handoff_target,),
            ).fetchone()
            if (
                not handoff_row
                or handoff_row["project_id"] != packet["project_id"]
                or handoff_row["archived"]
                or handoff_row["lifecycle"] not in {"active", "suspended"}
            ):
                raise AdapterError("handoff_target_unresolved")
        if not packet["acceptance_authority_session_id"] or not packet["acceptance_scope_id"]:
            raise AdapterError("acceptance_authority_missing")
        if packet["acceptance_authority_session_id"] == packet["target_session_id"]:
            raise AdapterError("self_acceptance_forbidden")
        if packet["target_kind"] == "main_session":
            if packet["session_resolution"] == "takeover" and not packet["handoff_receipt_id"]:
                raise AdapterError("handoff_receipt_missing")
            if packet["session_resolution"] == "reuse" and packet["target_session_id"] not in packet["candidate_session_ids"]:
                raise AdapterError("candidate_session_unresolved")
        if not isinstance(packet["max_attempts"], int) or packet["max_attempts"] < 1:
            raise AdapterError("max_attempts_invalid")
        if _expired(packet.get("lease_expires_at")):
            raise AdapterError("lease_expired")
        check = self.db.execute(
            "SELECT * FROM capability_checks WHERE check_id = ?", (capability_check_id,)
        ).fetchone()
        if not check or check["result"] != "ready" or check["operation"] != "dispatch":
            raise AdapterError("capability_gap")
        if (
            check["project_id"] != packet["project_id"]
            or check["plan_id"] != packet["plan_id"]
            or check["snapshot_id"] != packet["snapshot_id"]
        ):
            raise AdapterError("capability_check_mismatch")
        if check["target_kind"] != packet["target_kind"] or check["canonical_target_id"] != packet["target_session_id"]:
            raise AdapterError("capability_check_mismatch")
        available = set(json.loads(check["available_json"]))
        if not DISPATCH_CAPABILITIES[packet["target_kind"]].issubset(available):
            raise AdapterError("capability_gap")
        if not packet["target_session_id"] or packet["callback_to"] != packet["parent_session_id"]:
            raise AdapterError("target_unresolved")
        if packet["parent_session_id"]:
            parent = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (packet["parent_session_id"],)).fetchone()
            if not parent and packet["parent_session_id"] != packet["root_session_id"]:
                raise AdapterError("target_unresolved")
            if parent and (
                parent["project_id"] != packet["project_id"]
                or parent["archived"]
                or parent["lifecycle"] not in {"active", "suspended"}
            ):
                raise AdapterError("target_unresolved")
            if parent and packet["permission_boundary"] != parent["permission_boundary"]:
                raise AdapterError("permission_boundary_escalation")
        self._validate_dispatch_graph(packet)
        self._validate_dependency_graph(packet)
        self.resolve_project(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            plan_revision=packet["plan_revision"],
            snapshot_id=packet["snapshot_id"],
            commander_session_id=packet["root_session_id"],
            commander_epoch=packet["commander_epoch"],
            commander_lease_id=packet["commander_lease_id"],
            lease_expires_at=packet.get("lease_expires_at"),
            commit=False,
        )
        if packet["parent_session_id"]:
            parent = self.db.execute(
                "SELECT permission_boundary, project_id, archived, lifecycle FROM sessions WHERE session_id=?",
                (packet["parent_session_id"],),
            ).fetchone()
            if not parent or parent["project_id"] != packet["project_id"] or parent["archived"] or parent["lifecycle"] not in {"active", "suspended"}:
                raise AdapterError("target_unresolved")
            if parent["permission_boundary"] != packet["permission_boundary"]:
                raise AdapterError("permission_boundary_escalation")
        ancestors = list(packet["ancestor_session_ids"])
        if packet["parent_session_id"] in ancestors or packet["target_session_id"] in ancestors:
            raise AdapterError("cycle_detected")
        if packet["target_session_id"] == packet["parent_session_id"]:
            raise AdapterError("multiple_parent")
        existing_attempt = self.db.execute(
            "SELECT task_id, attempt_id FROM tasks WHERE attempt_id = ? OR dispatch_idempotency_key = ?",
            (packet["attempt_id"], packet["idempotency_key"]),
        ).fetchone()
        if existing_attempt:
            if existing_attempt["task_id"] != packet["task_id"] or existing_attempt["attempt_id"] != packet["attempt_id"]:
                raise AdapterError("idempotency_key_conflict")
            return {"result": "duplicate", "task_id": existing_attempt[0], "attempt_id": existing_attempt[1]}
        if profile["pattern"] == "fan_out":
            existing_fanout = self.db.execute(
                "SELECT task_id, attempt_id, state, packet_json FROM tasks WHERE project_id=?",
                (packet["project_id"],),
            ).fetchall()
            fanout_count = 0
            for row in existing_fanout:
                if row["task_id"] == packet["task_id"]:
                    # A retry creates a new active attempt for the same
                    # logical task and therefore consumes one active slot.
                    if row["attempt_id"] != packet["attempt_id"] and row["state"] in TERMINAL_STATES:
                        fanout_count += 1
                    continue
                existing_profile = json.loads(row["packet_json"]).get("coordination_profile", {})
                if (
                    existing_profile.get("pattern") == "fan_out"
                    and existing_profile.get("fanout_group_id") == profile["fanout_group_id"]
                    and row["state"] not in TERMINAL_STATES
                ):
                    fanout_count += 1
            if fanout_count >= profile["max_fanout"]:
                raise AdapterError("fanout_limit_exceeded")
        current_task = self.db.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (packet["task_id"],)
        ).fetchone()
        retrying = bool(current_task and current_task["attempt_id"] != packet["attempt_id"])
        session_lease = self.db.execute(
            "SELECT lease_id FROM sessions WHERE session_id=?", (packet["target_session_id"],)
        ).fetchone()
        if not retrying and session_lease and session_lease["lease_id"] != packet.get("lease_id"):
            raise AdapterError("stale_session_lease")
        if retrying:
            if current_task["state"] not in TERMINAL_STATES:
                raise AdapterError("retry_requires_sealed_attempt")
            previous_packet = json.loads(current_task["packet_json"])
            prior_attempts = self.db.execute(
                "SELECT count(*) FROM attempts WHERE task_id=?", (packet["task_id"],)
            ).fetchone()[0]
            max_attempts = min(int(previous_packet["max_attempts"]), int(packet["max_attempts"]))
            if int(prior_attempts) + 1 >= max_attempts:
                raise AdapterError("max_attempts_exceeded")
            for identity_field in ("project_id", "target_kind", "target_session_id", "parent_session_id", "root_session_id"):
                if previous_packet.get(identity_field) != packet.get(identity_field):
                    raise AdapterError("retry_identity_mismatch")
            if not packet.get("lease_id") or packet["lease_id"] == previous_packet.get("lease_id"):
                raise AdapterError("retry_lease_required")
            rotated = self.db.execute(
                "UPDATE sessions SET lease_id=?, lease_expires_at=?, updated_at=? WHERE session_id=? AND lease_id=?",
                (
                    packet["lease_id"], packet.get("lease_expires_at"), _now(),
                    packet["target_session_id"], previous_packet.get("lease_id"),
                ),
            )
            if rotated.rowcount != 1:
                raise AdapterError("stale_session_lease")
            self.db.execute(
                """INSERT OR IGNORE INTO attempts
                (attempt_id, task_id, project_id, packet_json, state, last_source_sequence,
                 cancel_epoch, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    current_task["attempt_id"],
                    current_task["task_id"],
                    current_task["project_id"],
                    current_task["packet_json"],
                    current_task["state"],
                    current_task["last_source_sequence"],
                    current_task["cancel_epoch"],
                    current_task["created_at"],
                    current_task["updated_at"],
                ),
            )
        existing_edge = self.db.execute(
            "SELECT parent_session_id FROM child_edges WHERE child_session_id = ?",
            (packet["target_session_id"],),
        ).fetchone()
        if existing_edge and existing_edge[0] != packet["parent_session_id"]:
            raise AdapterError("multiple_parent")
        if existing_edge and packet["target_kind"] == "internal_child" and not retrying:
            raise AdapterError("target_session_reused")
        self._ensure_session(
            session_id=packet["target_session_id"],
            project_id=packet["project_id"],
            role_id=packet.get("role_id") or None,
            parent_session_id=packet["parent_session_id"] or None,
            target_kind=packet["target_kind"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            permission_boundary=packet["permission_boundary"],
            owner_session_id=packet.get("previous_owner_session_id") or packet["parent_session_id"],
            lease_id=packet.get("lease_id"),
            lease_expires_at=packet.get("lease_expires_at"),
            role_epoch=int(packet.get("role_epoch") or 1),
        )
        session_row = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=?", (packet["target_session_id"],)
        ).fetchone()
        if not session_row or session_row["project_id"] != packet["project_id"] or session_row["target_kind"] != packet["target_kind"]:
            raise AdapterError("target_unresolved")
        if session_row["archived"] or session_row["lifecycle"] not in {"active", "suspended"}:
            raise AdapterError("target_unresolved")
        if session_row["lease_id"] != packet.get("lease_id"):
            raise AdapterError("stale_session_lease")
        if session_row["plan_id"] not in {None, packet["plan_id"]} or session_row["snapshot_id"] not in {None, packet["snapshot_id"]}:
            raise AdapterError("plan_drift")
        if packet["target_kind"] == "internal_child" and session_row["parent_session_id"] != packet["parent_session_id"]:
            raise AdapterError("multiple_parent")
        if session_row["permission_boundary"] != packet["permission_boundary"]:
            raise AdapterError("permission_boundary_mismatch")
        if packet["target_kind"] == "main_session":
            if session_row["role_id"] != packet["role_id"]:
                raise AdapterError("role_binding_mismatch")
            if int(session_row["role_epoch"]) != int(packet["role_epoch"]):
                raise AdapterError("stale_role_epoch")
            if packet["session_resolution"] == "takeover":
                handoff = self.db.execute(
                    """SELECT 1 FROM session_receipts
                    WHERE handoff_receipt_id=? AND session_id=? AND role_id=?
                    AND resolution='takeover' AND role_epoch=?""",
                    (
                        packet["handoff_receipt_id"],
                        packet["target_session_id"],
                        packet["role_id"],
                        int(packet["role_epoch"]),
                    ),
                ).fetchone()
                if not handoff:
                    raise AdapterError("handoff_receipt_invalid")
        authority = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active', 'suspended')",
            (packet["acceptance_authority_session_id"], packet["project_id"]),
        ).fetchone()
        if not authority:
            raise AdapterError("acceptance_authority_unresolved")
        if authority["permission_boundary"] != packet["acceptance_authority_permission_boundary"]:
            raise AdapterError("permission_boundary_mismatch")
        if packet["acceptance_mode"] == "commander_gate" and packet["acceptance_authority_session_id"] != packet["parent_session_id"]:
            raise AdapterError("acceptance_authority")
        if existing_edge:
            pass
        else:
            self.db.execute(
                "INSERT INTO child_edges(parent_session_id, child_session_id, status) VALUES (?, ?, 'open')",
                (packet["parent_session_id"], packet["target_session_id"]),
            )
        if retrying:
            self.db.execute(
                """UPDATE tasks SET project_id=?, attempt_id=?, dispatch_idempotency_key=?, packet_json=?,
                state='dispatched', last_source_sequence=NULL, cancel_epoch=?, updated_at=?
                WHERE task_id=?""",
                (
                    packet["project_id"],
                    packet["attempt_id"],
                    packet["idempotency_key"],
                    _json({**packet, "capability_check_id": capability_check_id}),
                    str(packet["cancel_epoch"]),
                    _now(),
                    packet["task_id"],
                ),
            )
        else:
            self.db.execute(
                """INSERT INTO tasks
            (task_id, project_id, attempt_id, dispatch_idempotency_key, packet_json, state, last_source_sequence,
             cancel_epoch, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'dispatched', NULL, ?, ?, ?)""",
            (
                packet["task_id"],
                packet["project_id"],
                packet["attempt_id"],
                packet["idempotency_key"],
                _json({**packet, "capability_check_id": capability_check_id}),
                str(packet["cancel_epoch"]),
                _now(),
                _now(),
            ),
            )
        dependency_state = self._dependency_barrier_state(
            packet["dependency_task_ids"], packet["join_policy"], packet
        )
        self.db.execute(
            """INSERT OR REPLACE INTO dependency_barriers
            (task_id, dependency_task_ids_json, join_policy, state, updated_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                packet["task_id"],
                _json(packet["dependency_task_ids"]),
                _json(packet["join_policy"]),
                dependency_state,
                _now(),
            ),
        )
        self._insert_event(
            event_id=_new_id("evt"),
            task_id=packet["task_id"],
            attempt_id=packet["attempt_id"],
            event_type="task.dispatched",
            status="dispatched",
            source_sequence=None,
            idempotency_key=f"{packet['idempotency_key']}/dispatched",
            payload={
                "packet": packet,
                "capability_check_id": capability_check_id,
                "receipt_origin": "adapter_generated",
                "observed_by": "host_adapter",
            },
        )
        return {"result": "dispatched", "task_id": packet["task_id"], "attempt_id": packet["attempt_id"]}

    def dispatch_to_host(
        self,
        packet: dict[str, Any],
        capability_check_id: str,
        send_callback: Callable[[dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        """Persist a dispatch, then bind it to a real host send receipt.

        ``dispatch`` remains the isolated state-machine primitive. This method
        is the explicit integration boundary for a real host. It refuses to
        create a task unless the preflight includes ``send_task`` and a sender
        callback is supplied. A non-confirmed send seals the attempt as
        ``unknown`` instead of allowing an unverified retry.
        """
        check = self.db.execute(
            "SELECT * FROM capability_checks WHERE check_id=?", (capability_check_id,)
        ).fetchone()
        if (
            not check
            or check["result"] != "ready"
            or check["operation"] != "dispatch"
            or check["transport"] != "host"
            or "send_task" not in set(json.loads(check["required_json"]))
        ):
            return {"result": "capability_gap", "missing": ["send_task"]}
        available = set(json.loads(check["available_json"]))
        if "send_task" not in available or send_callback is None:
            return {"result": "capability_gap", "missing": ["send_task"]}

        # The capability receipt is part of the immutable packet persisted by
        # dispatch(). Keep the caller's object untouched while ensuring the
        # transport callback and any unknown-send receipt see the same value.
        packet = dict(packet)
        packet["capability_check_id"] = capability_check_id

        existing = self.db.execute(
            "SELECT * FROM dispatch_deliveries WHERE task_id=? AND attempt_id=?",
            (packet.get("task_id"), packet.get("attempt_id")),
        ).fetchone()
        if existing:
            if existing["status"] == "pending":
                stored = self.db.execute(
                    "SELECT packet_json FROM tasks WHERE task_id=? AND attempt_id=?",
                    (existing["task_id"], existing["attempt_id"]),
                ).fetchone()
                if stored:
                    self._seal_transport_unknown(json.loads(stored["packet_json"]), existing["delivery_receipt_id"])
                self.db.execute(
                    "UPDATE dispatch_deliveries SET status='unknown', delivery_attempt=delivery_attempt+1 WHERE delivery_receipt_id=?",
                    (existing["delivery_receipt_id"],),
                )
                self.db.commit()
            return {
                "result": "unknown" if existing["status"] == "pending" else existing["status"],
                "task_id": existing["task_id"],
                "attempt_id": existing["attempt_id"],
                "delivery_receipt_id": existing["delivery_receipt_id"],
                "host_receipt_id": existing["host_receipt_id"],
            }

        persisted = self.dispatch(packet, capability_check_id)
        if persisted.get("result") == "duplicate":
            task = self.db.execute(
                "SELECT attempt_id, state FROM tasks WHERE task_id=?", (packet["task_id"],)
            ).fetchone()
            # A previous persistence-only call may have created the durable
            # dispatch receipt without binding a host delivery. Allow this
            # method to complete that binding, but never reopen another state.
            if not task or task["attempt_id"] != packet["attempt_id"] or task["state"] != "dispatched":
                return persisted

        delivery_receipt_id = f"{packet['task_id']}/{packet['attempt_id']}/dispatch"
        self.db.execute(
            """INSERT OR IGNORE INTO dispatch_deliveries
            (delivery_receipt_id, task_id, attempt_id, target_session_id, status,
             host_receipt_id, delivery_attempt, acknowledged_at, created_at)
            VALUES (?, ?, ?, ?, 'pending', '', 1, NULL, ?)""",
            (delivery_receipt_id, packet["task_id"], packet["attempt_id"], packet["target_session_id"], _now()),
        )
        self.db.commit()
        try:
            raw_result = send_callback(dict(packet))
        except Exception:
            raw_result = None
        delivered = False
        host_receipt_id = ""
        if isinstance(raw_result, dict) and raw_result.get("status") == "delivered":
            target_matches = not raw_result.get("target_session_id") or raw_result.get("target_session_id") == packet["target_session_id"]
            attempt_matches = not raw_result.get("attempt_id") or raw_result.get("attempt_id") == packet["attempt_id"]
            host_receipt_id = str(raw_result.get("host_receipt_id") or "")
            delivered = target_matches and attempt_matches and bool(host_receipt_id)
        elif raw_result is True:
            # A boolean success is accepted only as a host delivery signal;
            # the durable adapter receipt remains the canonical identifier.
            delivered = True

        status = "delivered" if delivered else "unknown"
        self.db.execute(
            """UPDATE dispatch_deliveries SET status=?, host_receipt_id=?,
            acknowledged_at=?, delivery_attempt=delivery_attempt+1
            WHERE delivery_receipt_id=?""",
            (
                status,
                host_receipt_id,
                _now() if delivered else None,
                delivery_receipt_id,
            ),
        )
        if not delivered:
            self._seal_transport_unknown(packet, delivery_receipt_id)
        self.db.commit()
        return {
            "result": status,
            "task_id": packet["task_id"],
            "attempt_id": packet["attempt_id"],
            "delivery_receipt_id": delivery_receipt_id,
            "host_receipt_id": host_receipt_id,
        }

    def record_event(
        self,
        event: dict[str, Any],
        wake_callback: Callable[[str, str], bool] | None = None,
    ) -> dict[str, Any]:
        event = _with_default_coordination_profile(event)
        event = _with_default_receipt_provenance(event)
        missing = sorted(EVENT_FIELDS - event.keys())
        if missing:
            raise AdapterError(f"event_missing:{','.join(missing)}")
        if event["schema_version"] != SCHEMA_VERSION:
            raise AdapterError("schema_unsupported")
        expected = EVENT_STATUS.get(event["event_type"])
        if expected != event["status"]:
            raise AdapterError("event_status_mismatch")
        if event["receipt_origin"] not in RECEIPT_ORIGINS:
            raise AdapterError("receipt_origin_invalid")
        if event["receipt_origin"] == "host_observed" and not event["observed_by"]:
            raise AdapterError("observed_by_missing")
        duplicate = self.db.execute(
            "SELECT event_id, task_id, attempt_id FROM events WHERE event_id = ? OR idempotency_key = ?",
            (event["event_id"], event["idempotency_key"]),
        ).fetchone()
        if duplicate:
            if duplicate["task_id"] != event["task_id"] or duplicate["attempt_id"] != event["attempt_id"]:
                raise AdapterError("idempotency_key_conflict")
            return {"result": "duplicate", "event_id": duplicate[0]}
        task = self.db.execute("SELECT * FROM tasks WHERE task_id = ?", (event["task_id"],)).fetchone()
        historical_attempt = False
        if not task or task["attempt_id"] != event["attempt_id"]:
            task = self.db.execute(
                "SELECT * FROM attempts WHERE task_id=? AND attempt_id=?",
                (event["task_id"], event["attempt_id"]),
            ).fetchone()
            historical_attempt = task is not None
        if not task:
            raise AdapterError("target_unresolved")
        packet = _with_default_coordination_profile(json.loads(task["packet_json"]))
        self._validate_identity(packet, event)
        if event["event_type"] in {"task.accepted", "task.rejected"}:
            authority_id = packet["acceptance_authority_session_id"]
            if event["emitted_by_session_id"] != authority_id:
                raise AdapterError("acceptance_authority")
            self._authenticate_emitter(packet, event, authority_id)
            if event["event_type"] == "task.accepted":
                if not event.get("accepted_for_event_id"):
                    raise AdapterError("acceptance_reference_missing")
                referenced = self.db.execute(
                    """SELECT event_type, status FROM events
                    WHERE event_id=? AND task_id=? AND attempt_id=?""",
                    (event["accepted_for_event_id"], event["task_id"], event["attempt_id"]),
                ).fetchone()
                if not referenced or referenced["event_type"] not in {"task.completed_claim", "task.partial"}:
                    raise AdapterError("acceptance_reference_invalid")
                if event.get("validated_by_session_id") != authority_id or not event.get("validation_evidence_refs"):
                    raise AdapterError("validation_evidence_missing")
                if packet["acceptance_mode"] == "independent_validator" and not event.get("validation_receipt_id"):
                    raise AdapterError("validation_receipt_missing")
            elif not event.get("rejection_reasons"):
                raise AdapterError("rejection_reason_missing")
        else:
            parent_events = {"task.waiting", "task.cancelled", "task.unknown"}
            emitter = event["emitted_by_session_id"]
            adapter_events = {"task.failed", "task.cancelled", "task.unknown"}
            if event["receipt_origin"] == "adapter_generated" and emitter == "host_adapter" and event["event_type"] in adapter_events:
                pass
            elif event["event_type"] in parent_events and emitter == packet["parent_session_id"]:
                self._authenticate_emitter(packet, event, emitter, allow_superseded_epoch=True)
            elif event["event_type"] in {"task.started", "task.progress", "task.completed_claim", "task.partial", "task.blocked", "task.failed"} and emitter == packet["target_session_id"]:
                self._authenticate_emitter(packet, event, emitter, allow_superseded_epoch=True)
            else:
                raise AdapterError("source_authentication")
        if packet["target_kind"] == "main_session":
            session = self.db.execute(
                "SELECT role_epoch FROM sessions WHERE session_id=?", (packet["target_session_id"],)
            ).fetchone()
            if not session or int(session["role_epoch"]) != int(packet["role_epoch"]):
                return self._record_stale(event, "superseded_role_epoch")
        if historical_attempt:
            return self._record_stale(event, "sealed_attempt")
        if packet["parent_session_id"]:
            parent_state = self.db.execute(
                "SELECT archived, lifecycle FROM sessions WHERE session_id=?", (packet["parent_session_id"],)
            ).fetchone()
            if parent_state and (parent_state["archived"] or parent_state["lifecycle"] not in {"active", "suspended"}):
                return self._record_stale(event, "parent_session_closed")
        current = task["state"]
        if current in TERMINAL_STATES:
            return self._record_stale(event, "sealed_attempt")
        if event["event_type"] in {"task.started", "task.progress"}:
            barrier = self.db.execute(
                "SELECT dependency_task_ids_json, join_policy FROM dependency_barriers WHERE task_id=?",
                (event["task_id"],),
            ).fetchone()
            if barrier:
                barrier_state = self._dependency_barrier_state(
                    json.loads(barrier["dependency_task_ids_json"]),
                    json.loads(barrier["join_policy"]),
                    packet,
                )
                if barrier_state != "ready":
                    raise AdapterError("dependency_barrier_unmet")
        if event["event_type"] in {"task.accepted", "task.rejected"} and packet["acceptance_mode"] == "independent_validator":
            if not event.get("validation_receipt_id"):
                raise AdapterError("validation_receipt_missing")
            receipt_conflict = self.db.execute(
                """SELECT task_id, attempt_id FROM acceptance_receipts
                WHERE validation_receipt_id=?""",
                (event["validation_receipt_id"],),
            ).fetchone()
            if receipt_conflict:
                if receipt_conflict["task_id"] == event["task_id"] and receipt_conflict["attempt_id"] == event["attempt_id"]:
                    return self._record_stale(event, "duplicate_validation_receipt")
                raise AdapterError("validation_receipt_conflict")
            prior_validation = self.db.execute(
                """SELECT validation_receipt_id FROM acceptance_receipts
                WHERE acceptance_scope_id=? AND task_id=? AND attempt_id=?""",
                (packet["acceptance_scope_id"], event["task_id"], event["attempt_id"]),
            ).fetchone()
            if prior_validation:
                return self._record_stale(event, "duplicate_acceptance_scope")
        target_state = event["status"]
        if target_state in TERMINAL_STATES and target_state not in packet["coordination_profile"]["termination_conditions"]:
            raise AdapterError("termination_condition_violation")
        if target_state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise AdapterError("invalid_transition")
        sequence = event["sequence"]
        if not isinstance(sequence, int) or sequence < 1:
            raise AdapterError("invalid_sequence")
        last_sequence = task["last_source_sequence"]
        if last_sequence is not None and sequence != last_sequence + 1:
            return self._record_stale(event, "sequence_gap_or_replay")
        self._insert_event(
            event_id=event["event_id"],
            task_id=event["task_id"],
            attempt_id=event["attempt_id"],
            event_type=event["event_type"],
            status=target_state,
            source_sequence=sequence,
            idempotency_key=event["idempotency_key"],
            payload=event,
        )
        if event["event_type"] in {"task.accepted", "task.rejected"} and packet["acceptance_mode"] == "independent_validator":
            self.db.execute(
                """INSERT INTO acceptance_receipts
                (validation_receipt_id, acceptance_scope_id, task_id, attempt_id,
                 validator_session_id, verdict, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event["validation_receipt_id"],
                    packet["acceptance_scope_id"],
                    event["task_id"],
                    event["attempt_id"],
                    event["emitted_by_session_id"],
                    event["status"],
                    _now(),
                ),
            )
        if event["event_type"] in {"task.cancelled", "task.unknown"}:
            next_cancel_epoch = f"{packet['cancel_epoch']}:{event['status']}"
            self.db.execute(
                "UPDATE tasks SET state=?, last_source_sequence=?, cancel_epoch=?, updated_at=? WHERE task_id=?",
                (target_state, sequence, next_cancel_epoch, _now(), event["task_id"]),
            )
        else:
            self.db.execute(
                "UPDATE tasks SET state=?, last_source_sequence=?, updated_at=? WHERE task_id=?",
                (target_state, sequence, _now(), event["task_id"]),
            )
        self._refresh_dependency_barriers()
        self.db.commit()
        wake = None
        if packet["parent_session_id"]:
            wake = self.wake_session(packet["parent_session_id"], event["event_id"], wake_callback)
        return {"result": "accepted", "event_id": event["event_id"], "status": target_state, "wake": wake}

    def mark_plan_drift(self, task_id: str, by_session_id: str, reason: str = "plan_drift") -> dict[str, Any]:
        task = self.db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise AdapterError("target_unresolved")
        if task["state"] in TERMINAL_STATES:
            return {"result": "duplicate", "task_id": task_id}
        packet = _with_default_coordination_profile(json.loads(task["packet_json"]))
        actor = self.db.execute(
            "SELECT session_id, project_id, target_kind, archived, lifecycle FROM sessions WHERE session_id=?",
            (by_session_id,),
        ).fetchone()
        if not actor or actor["project_id"] != packet["project_id"] or actor["archived"] or actor["lifecycle"] not in {"active", "suspended"}:
            raise AdapterError("source_authentication")
        if actor["session_id"] != packet["root_session_id"] or actor["target_kind"] != "commander":
            raise AdapterError("source_authentication")
        project = self.db.execute(
            "SELECT commander_epoch, commander_lease_id, lease_expires_at FROM projects WHERE project_id=? AND active=1",
            (packet["project_id"],),
        ).fetchone()
        if (
            not project
            or project["commander_epoch"] != packet["commander_epoch"]
            or project["commander_lease_id"] != packet["commander_lease_id"]
            or _expired(project["lease_expires_at"])
        ):
            raise AdapterError("stale_commander_epoch")
        event_id = _new_id("evt")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "event_type": "task.stale",
            "status": "stale",
            "project_id": packet["project_id"],
            "plan_id": packet["plan_id"],
            "plan_revision": packet["plan_revision"],
            "snapshot_id": packet["snapshot_id"],
            "snapshot_hash": packet["snapshot_hash"],
            "capability_check_id": packet["capability_check_id"],
            "permission_boundary": packet["permission_boundary"],
            "task_id": task_id,
            "attempt_id": task["attempt_id"],
            "task_contract_hash": packet["task_contract_hash"],
            "root_session_id": packet["root_session_id"],
            "session_id": packet["target_session_id"],
            "target_session_id": packet["target_session_id"],
            "parent_session_id": packet["parent_session_id"],
            "callback_to": packet["callback_to"],
            "commander_epoch": packet.get("commander_epoch", ""),
            "session_resolution": packet["session_resolution"],
            "candidate_session_ids": packet["candidate_session_ids"],
            "role_id": packet["role_id"],
            "role_epoch": packet["role_epoch"],
            "previous_owner_session_id": packet["previous_owner_session_id"],
            "handoff_receipt_id": packet["handoff_receipt_id"],
            "acceptance_mode": packet["acceptance_mode"],
            "acceptance_authority_session_id": packet["acceptance_authority_session_id"],
            "acceptance_authority_permission_boundary": packet["acceptance_authority_permission_boundary"],
            "acceptance_scope_id": packet["acceptance_scope_id"],
            "coordination_profile": packet["coordination_profile"],
            "validation_receipt_id": "",
            "accepted_for_event_id": "",
            "validated_by_session_id": "",
            "validation_evidence_refs": [],
            "rejection_reasons": [],
            "emitted_by_session_id": by_session_id,
            "sequence": None,
            "idempotency_key": f"{packet['idempotency_key']}/stale/{reason}",
            "stale_reason": reason,
            "stale_by_session_id": by_session_id,
        }
        self._insert_event(
            event_id=event_id,
            task_id=task_id,
            attempt_id=task["attempt_id"],
            event_type="task.stale",
            status="stale",
            source_sequence=None,
            idempotency_key=payload["idempotency_key"],
            payload=payload,
            stale_reason=reason,
        )
        self.db.execute(
            "UPDATE tasks SET state='stale', cancel_epoch=?, updated_at=? WHERE task_id=?",
            (f"{packet['cancel_epoch']}:drift", _now(), task_id),
        )
        self.db.execute(
            "UPDATE attempts SET state='stale', cancel_epoch=? WHERE task_id=? AND attempt_id=?",
            (f"{packet['cancel_epoch']}:drift", task_id, task["attempt_id"]),
        )
        self.db.execute(
            "UPDATE sessions SET lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE session_id=?",
            (_now(), packet["target_session_id"]),
        )
        self.db.execute(
            "UPDATE child_edges SET status='stale' WHERE child_session_id=?", (packet["target_session_id"],)
        )
        self.db.commit()
        return {"result": "stale", "event_id": event_id, "task_id": task_id}

    def archive_session(
        self,
        session_id: str,
        archive_callback: Callable[[str], bool] | None = None,
        *,
        actor_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Archive only after host confirmation and an authorized actor check."""
        session = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not session:
            return {"result": "target_unresolved", "session_id": session_id}
        if not actor_session_id:
            return {"result": "authorization_required", "session_id": session_id}
        actor = self.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND archived=0 AND lifecycle IN ('active','suspended')",
            (actor_session_id, session["project_id"]),
        ).fetchone()
        if not actor or (actor_session_id != session["owner_session_id"] and actor["target_kind"] != "commander"):
            return {"result": "source_authentication", "session_id": session_id}
        if archive_callback is None:
            return {"result": "capability_gap", "missing": ["archive_session"]}
        active_children = self.db.execute(
            "SELECT 1 FROM child_edges WHERE parent_session_id=? AND status='open' LIMIT 1",
            (session_id,),
        ).fetchone()
        if active_children:
            return {"result": "children_active", "session_id": session_id}
        if not archive_callback(session_id):
            return {"result": "unknown", "session_id": session_id}
        self.db.execute(
            "UPDATE sessions SET archived=1, lifecycle='closed', lease_id=NULL, lease_expires_at=NULL, updated_at=? WHERE session_id=?",
            (_now(), session_id),
        )
        self.db.execute("UPDATE child_edges SET status='closed' WHERE child_session_id=?", (session_id,))
        self.db.commit()
        return {"result": "archived", "session_id": session_id}

    def _validate_identity(self, packet: dict[str, Any], event: dict[str, Any]) -> None:
        for field in (
            "project_id",
            "plan_id",
            "plan_revision",
            "snapshot_id",
            "snapshot_hash",
            "capability_check_id",
            "task_contract_hash",
            "permission_boundary",
            "root_session_id",
            "target_session_id",
            "parent_session_id",
            "callback_to",
            "commander_epoch",
            "session_resolution",
            "candidate_session_ids",
            "role_id",
            "role_epoch",
            "previous_owner_session_id",
            "handoff_receipt_id",
            "acceptance_mode",
            "acceptance_authority_session_id",
            "acceptance_authority_permission_boundary",
            "acceptance_scope_id",
            "coordination_profile",
            "cancel_epoch",
        ):
            if event.get(field) != packet.get(field):
                raise AdapterError(f"identity_mismatch:{field}")
        if event.get("session_id") != packet.get("target_session_id"):
            raise AdapterError("identity_mismatch:session_id")

    def _record_stale(self, event: dict[str, Any], reason: str) -> dict[str, Any]:
        event = _with_default_receipt_provenance(event)
        event["receipt_origin"] = "adapter_generated"
        event["observed_by"] = "host_adapter"
        self._insert_event(
            event_id=event["event_id"],
            task_id=event["task_id"],
            attempt_id=event["attempt_id"],
            event_type="task.stale",
            status="stale",
            source_sequence=event.get("sequence"),
            idempotency_key=event["idempotency_key"],
            payload=event,
            stale_reason=reason,
        )
        self.db.commit()
        return {"result": "stale", "event_id": event["event_id"], "reason": reason}

    def _seal_transport_unknown(self, packet: dict[str, Any], delivery_receipt_id: str) -> None:
        """Seal a persisted dispatch when the host send outcome is uncertain."""
        event_id = _new_id("evt")
        payload = event_template(packet, "task.unknown", 1)
        payload.update(
            {
                "event_id": event_id,
                "attempt_id": packet["attempt_id"],
                "sequence": None,
                "emitted_by_session_id": packet["root_session_id"],
                "receipt_origin": "adapter_generated",
                "observed_by": "host_transport",
                "unknown_reason": "dispatch_delivery_unknown",
                "delivery_receipt_id": delivery_receipt_id,
                "idempotency_key": f"{packet['idempotency_key']}/unknown/dispatch",
            }
        )
        self._insert_event(
            event_id=event_id,
            task_id=packet["task_id"],
            attempt_id=packet["attempt_id"],
            event_type="task.unknown",
            status="unknown",
            source_sequence=None,
            idempotency_key=payload["idempotency_key"],
            payload=payload,
        )
        self.db.execute(
            "UPDATE tasks SET state='unknown', updated_at=? WHERE task_id=? AND attempt_id=?",
            (_now(), packet["task_id"], packet["attempt_id"]),
        )

    def _insert_event(
        self,
        *,
        event_id: str,
        task_id: str,
        attempt_id: str,
        event_type: str,
        status: str,
        source_sequence: int | None,
        idempotency_key: str,
        payload: dict[str, Any],
        stale_reason: str | None = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO events
            (event_id, task_id, attempt_id, event_type, status, source_sequence,
             receipt_sequence, idempotency_key, payload_json, stale_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                task_id,
                attempt_id,
                event_type,
                status,
                source_sequence,
                self._next_receipt_sequence(),
                idempotency_key,
                _json(payload),
                stale_reason,
                _now(),
            ),
        )


def packet_template(target_session_id: str = "child-1") -> dict[str, Any]:
    """Return a complete isolated packet useful to adapter integrators."""
    return ContractPacket({
        "schema_version": SCHEMA_VERSION,
        "project_id": "project-test",
        "plan_id": "plan-test",
        "plan_revision": "1",
        "snapshot_id": "snapshot-test",
        "snapshot_hash": "sha256:test",
        "capability_check_id": "",
        "permission_boundary": "",
        "session_resolution": "new",
        "candidate_session_ids": [],
        "role_epoch": 1,
        "previous_owner_session_id": "",
        "handoff_receipt_id": "",
        "acceptance_mode": "commander_gate",
        "acceptance_authority_session_id": "commander-1",
        "acceptance_authority_permission_boundary": "",
        "acceptance_scope_id": "acceptance-test",
        "task_id": "task-test",
        "attempt_id": "attempt-test",
        "root_session_id": "commander-1",
        "parent_session_id": "commander-1",
        "target_kind": "internal_child",
        "target_session_id": target_session_id,
        "role_id": "",
        "commander_epoch": "epoch-test",
        "ancestor_session_ids": [],
        "dispatch_depth": 1,
        "dependency_task_ids": [],
        "join_policy": "none",
        "objective": "test",
        "allowed_scope": ["read-only"],
        "excluded_scope": ["writes"],
        "acceptance_criteria": ["structured callback"],
        "acceptance_policy_version": "1",
        "inputs_and_evidence_refs": [],
        "output_contract": ["event envelope"],
        "side_effects_policy": "none",
        "lease_id": "lease-test",
        "commander_lease_id": "commander-lease-test",
        "lease_expires_at": "2099-01-01T00:00:00Z",
        "cancel_epoch": "0",
        "max_attempts": 1,
        "budget_and_deadline": "test",
        "coordination_profile": {
            "pattern": "sequential",
            "sop_id": "",
            "sop_step": "",
            "fanout_group_id": "",
            "max_fanout": 0,
            "route_key": "",
            "handoff_target_session_id": "",
            "termination_conditions": ["accepted", "rejected", "blocked", "failed", "cancelled", "unknown"],
        },
        "callback_to": "commander-1",
        "task_contract_hash": "",
        "idempotency_key": "project-test/task-test/attempt-test",
    })


def event_template(packet: dict[str, Any], event_type: str = "task.started", sequence: int = 1) -> dict[str, Any]:
    packet = _with_default_coordination_profile(packet)
    status = EVENT_STATUS[event_type]
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": _new_id("evt"),
        "event_type": event_type,
        "status": status,
        "project_id": packet["project_id"],
        "plan_id": packet["plan_id"],
        "plan_revision": packet["plan_revision"],
        "snapshot_id": packet["snapshot_id"],
        "snapshot_hash": packet["snapshot_hash"],
        "capability_check_id": packet["capability_check_id"],
        "permission_boundary": packet["permission_boundary"],
        "task_id": packet["task_id"],
        "attempt_id": packet["attempt_id"],
        "task_contract_hash": packet["task_contract_hash"],
        "root_session_id": packet["root_session_id"],
        "session_id": packet["target_session_id"],
        "target_session_id": packet["target_session_id"],
        "parent_session_id": packet["parent_session_id"],
        "callback_to": packet["callback_to"],
        "commander_epoch": packet["commander_epoch"],
        "session_resolution": packet["session_resolution"],
        "candidate_session_ids": packet["candidate_session_ids"],
        "role_id": packet["role_id"],
        "role_epoch": packet["role_epoch"],
        "previous_owner_session_id": packet["previous_owner_session_id"],
        "handoff_receipt_id": packet["handoff_receipt_id"],
        "acceptance_mode": packet["acceptance_mode"],
        "acceptance_authority_session_id": packet["acceptance_authority_session_id"],
        "acceptance_authority_permission_boundary": packet["acceptance_authority_permission_boundary"],
        "acceptance_scope_id": packet["acceptance_scope_id"],
        "coordination_profile": packet["coordination_profile"],
        "cancel_epoch": packet["cancel_epoch"],
        "validation_receipt_id": "",
        "accepted_for_event_id": "",
        "validated_by_session_id": "",
        "validation_evidence_refs": [],
        "rejection_reasons": [],
        "emitted_by_session_id": packet["target_session_id"],
        "receipt_origin": (
            "parent_recorded" if event_type in {"task.accepted", "task.rejected", "task.cancelled", "task.unknown"}
            else "adapter_generated" if event_type in {"task.dispatched", "task.stale"}
            else "worker_reported"
        ),
        "observed_by": "",
        "sequence": sequence,
        "receipt_sequence": None,
        "idempotency_key": f"{packet['idempotency_key']}/event/{sequence}/{event_type}",
    }
