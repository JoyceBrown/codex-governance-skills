"""Focused regression tests for the reference project-agent adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from host_adapter import AdapterError, HostAdapter, _contract_digest, _with_default_coordination_profile, event_template, packet_template, rotation_recommendation


class HostAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pao-adapter-")
        self.adapter = HostAdapter(Path(self.temp.name) / "receipts.sqlite")

    def tearDown(self) -> None:
        self.adapter.close()
        self.temp.cleanup()

    def test_rotation_recommendation_is_conservative_and_bounded(self) -> None:
        self.assertEqual(rotation_recommendation(), {"decision": "continue", "action": "continue", "reasons": [], "safe_boundary_required": True, "context_fraction": None, "compaction_count": 0})
        first = rotation_recommendation(compaction_count=1, context_fraction=0.81)
        self.assertEqual(first["decision"], "prepare_rotation")
        second = rotation_recommendation(compaction_count=2)
        self.assertEqual(second["decision"], "rotate_now")
        self.assertEqual(rotation_recommendation(instruction_drift=True)["decision"], "rotate_now")
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            rotation_recommendation(context_fraction=1.1)

    def _packet(self, child: str = "child-1", max_attempts: int | None = None) -> dict:
        packet = packet_template(child)
        if max_attempts is not None:
            packet["max_attempts"] = max_attempts
        suffix = child.replace("child-", "")
        packet["task_id"] = f"task-{suffix}"
        packet["attempt_id"] = f"attempt-{suffix}"
        packet["idempotency_key"] = f"project-test/task-{suffix}/attempt-{suffix}"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind=packet["target_kind"],
            canonical_target_id=child,
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=packet["parent_session_id"],
        )
        self.assertEqual(check["result"], "ready")
        packet["capability_check_id"] = check["capability_check_id"]
        self.assertEqual(self.adapter.dispatch(packet, packet["capability_check_id"])["result"], "dispatched")
        return packet

    def test_capability_gap_blocks_dispatch_without_task(self) -> None:
        packet = packet_template()
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="main_session",
            canonical_target_id="main-1",
            available_capabilities=set(),
            checked_by="commander-1",
        )
        self.assertEqual(check["result"], "capability_gap")
        packet["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "capability_gap"):
            self.adapter.dispatch(packet, check["capability_check_id"])
        self.assertEqual(self.adapter.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)

    def test_event_pair_identity_terminal_and_duplicate_rules(self) -> None:
        packet = self._packet()
        started = event_template(packet, "task.started", 1)
        self.assertEqual(self.adapter.record_event(started)["result"], "accepted")
        claim = event_template(packet, "task.completed_claim", 2)
        self.assertEqual(self.adapter.record_event(claim)["result"], "accepted")
        accepted = event_template(packet, "task.accepted", 3)
        accepted["emitted_by_session_id"] = packet["parent_session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = packet["parent_session_id"]
        accepted["validation_evidence_refs"] = ["test-evidence"]
        accepted["idempotency_key"] += "/accepted"
        self.assertEqual(self.adapter.record_event(accepted)["result"], "accepted")
        self.assertEqual(self.adapter.record_event(accepted)["result"], "duplicate")
        late = event_template(packet, "task.progress", 4)
        self.assertEqual(self.adapter.record_event(late)["result"], "stale")
        bad = event_template(packet, "task.waiting", 5)
        bad["status"] = "completed_claim"
        with self.assertRaisesRegex(AdapterError, "event_status_mismatch"):
            self.adapter.record_event(bad)

    def test_incomplete_text_callback_is_rejected(self) -> None:
        packet = self._packet("child-incomplete")
        incomplete = {
            "event_type": "task.completed_claim",
            "status": "completed_claim",
            "task_id": packet["task_id"],
            "attempt_id": packet["attempt_id"],
            "sequence": 1,
        }
        with self.assertRaisesRegex(AdapterError, "event_missing"):
            self.adapter.record_event(incomplete)

    def test_host_observed_receipt_requires_observer_identity(self) -> None:
        packet = self._packet("child-observed")
        observed = event_template(packet, "task.started", 1)
        observed["receipt_origin"] = "host_observed"
        with self.assertRaisesRegex(AdapterError, "observed_by_missing"):
            self.adapter.record_event(observed)
        observed["observed_by"] = "codex-host-test"
        self.assertEqual(self.adapter.record_event(observed)["result"], "accepted")

    def test_unknown_and_plan_drift_seal_attempts(self) -> None:
        packet = self._packet("child-unknown")
        started = event_template(packet, "task.started", 1)
        self.adapter.record_event(started)
        unknown = event_template(packet, "task.unknown", 2)
        unknown["emitted_by_session_id"] = packet["parent_session_id"]
        self.assertEqual(self.adapter.record_event(unknown)["result"], "accepted")
        late = event_template(packet, "task.completed_claim", 3)
        self.assertEqual(self.adapter.record_event(late)["result"], "stale")

        drift_packet = self._packet("child-drift")
        self.assertEqual(self.adapter.mark_plan_drift(drift_packet["task_id"], "commander-1")["result"], "stale")
        self.assertEqual(
            self.adapter.db.execute("SELECT state FROM tasks WHERE task_id=?", (drift_packet["task_id"],)).fetchone()[0],
            "stale",
        )

    def test_event_receipt_fences_old_project_epoch_without_manual_mark(self) -> None:
        packet = self._packet("child-fenced")
        self.adapter.db.execute(
            "UPDATE projects SET commander_epoch='epoch-new', commander_lease_id='lease-new' WHERE project_id=?",
            (packet["project_id"],),
        )
        self.adapter.db.commit()
        result = self.adapter.record_event(event_template(packet, "task.started", 1))
        self.assertEqual(result["result"], "stale")
        self.assertEqual(result["reason"], "stale_commander_epoch")
        self.assertEqual(
            self.adapter.db.execute("SELECT state FROM tasks WHERE task_id=?", (packet["task_id"],)).fetchone()[0],
            "stale",
        )

    def test_handoff_can_seal_unaccepted_completion_claim_as_unknown(self) -> None:
        packet = self._packet("child-handoff-unaccepted")
        self.adapter.record_event(event_template(packet, "task.started", 1))
        claim = event_template(packet, "task.completed_claim", 2)
        self.assertEqual(self.adapter.record_event(claim)["status"], "completed_claim")
        unknown = event_template(packet, "task.unknown", 3)
        unknown["emitted_by_session_id"] = packet["parent_session_id"]
        self.assertEqual(self.adapter.record_event(unknown)["status"], "unknown")
        attempt = self.adapter.reconcile_attempt(
            project_id=packet["project_id"], task_id=packet["task_id"], attempt_id=packet["attempt_id"]
        )
        self.assertEqual(attempt["state"], "unknown")
        self.assertNotEqual(attempt["cancel_epoch"], packet["cancel_epoch"])
        accepted = event_template(packet, "task.accepted", 4)
        accepted["emitted_by_session_id"] = packet["parent_session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = packet["parent_session_id"]
        accepted["validation_evidence_refs"] = ["late-check"]
        self.assertEqual(self.adapter.record_event(accepted)["result"], "stale")

    def test_cleanup_requires_real_host_callback_and_closes_edge(self) -> None:
        packet = self._packet("child-cleanup")
        self.assertEqual(self.adapter.archive_session(packet["target_session_id"], actor_session_id="commander-1")["result"], "capability_gap")
        self.assertEqual(
            self.adapter.archive_session(packet["target_session_id"], lambda session_id: session_id == "child-cleanup", actor_session_id="commander-1")["result"],
            "archived",
        )
        self.assertEqual(
            self.adapter.db.execute("SELECT status FROM child_edges WHERE child_session_id=?", ("child-cleanup",)).fetchone()[0],
            "closed",
        )

    def test_expired_role_can_be_retired_and_recreated_without_handoff(self) -> None:
        old = self._role_candidate()
        retired = self.adapter.retire_role_session(
            old["session_id"],
            lambda session_id: session_id == old["session_id"],
            actor_session_id="commander-1",
            reason="role_expired",
        )
        self.assertEqual(retired["result"], "retired")
        fresh = self.adapter.create_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-1",
        )
        self.assertNotEqual(fresh["session_id"], old["session_id"])
        self.assertEqual(
            [item["session_id"] for item in self.adapter.list_role_sessions(
                project_id="project-test", role_id="role-review"
            )],
            [fresh["session_id"]],
        )

    def test_fresh_project_start_replaces_expired_commander_without_checkpoint(self) -> None:
        self.adapter.resolve_project(
            project_id="project-test",
            plan_id="plan-old",
            plan_revision="1",
            snapshot_id="snapshot-old",
            commander_session_id="commander-old",
            commander_epoch="epoch-old",
            commander_lease_id="lease-old",
            lease_expires_at="2000-01-01T00:00:00Z",
        )
        result = self.adapter.resolve_project(
            project_id="project-test",
            plan_id="plan-new",
            plan_revision="2",
            snapshot_id="snapshot-new",
            commander_session_id="commander-new",
            commander_epoch="epoch-new",
            commander_lease_id="lease-new",
            lease_expires_at="2099-01-01T00:00:00Z",
            fresh_start=True,
            archive_callback=lambda session_id: session_id == "commander-old",
            authorized_actor="commander-old",
        )
        self.assertEqual(result["result"], "fresh_started")
        self.assertEqual(result["old_commander_session_id"], "commander-old")
        self.assertEqual(
            self.adapter.db.execute(
                "SELECT commander_session_id, plan_id FROM projects WHERE project_id=?",
                ("project-test",),
            ).fetchone()[0:2],
            ("commander-new", "plan-new"),
        )

    def test_fresh_project_binding_failure_rolls_back_project_row(self) -> None:
        self.adapter.resolve_project(
            project_id="project-test",
            plan_id="plan-old",
            plan_revision="1",
            snapshot_id="snapshot-old",
            commander_session_id="commander-old",
            commander_epoch="epoch-old",
            commander_lease_id="lease-old",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        self.adapter.register_session(
            session_id="commander-new",
            project_id="project-test",
            role_id="role-conflict",
            parent_session_id="commander-old",
            target_kind="main_session",
            plan_id="plan-old",
            snapshot_id="snapshot-old",
            owner_session_id="commander-old",
            lease_id="role-lease",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        with self.assertRaisesRegex(AdapterError, "session_id_reused"):
            self.adapter.resolve_project(
                project_id="project-test",
                plan_id="plan-new",
                plan_revision="2",
                snapshot_id="snapshot-new",
                commander_session_id="commander-new",
                commander_epoch="epoch-new",
                commander_lease_id="lease-new",
                lease_expires_at="2099-01-01T00:00:00Z",
                fresh_start=True,
                archive_callback=lambda _session_id: True,
                authorized_actor="commander-old",
            )
        row = self.adapter.db.execute(
            "SELECT commander_session_id, plan_id FROM projects WHERE project_id=?",
            ("project-test",),
        ).fetchone()
        self.assertEqual(tuple(row), ("commander-old", "plan-old"))

    def test_role_owner_must_belong_to_the_same_project(self) -> None:
        self.adapter.register_session(
            session_id="commander-1", project_id="project-test", role_id=None,
            parent_session_id=None, target_kind="commander", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-1",
            lease_id="lease-1", lease_expires_at="2099-01-01T00:00:00Z",
        )
        self.adapter.register_session(
            session_id="commander-2", project_id="project-other", role_id=None,
            parent_session_id=None, target_kind="commander", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-2",
            lease_id="lease-2", lease_expires_at="2099-01-01T00:00:00Z",
        )
        with self.assertRaisesRegex(AdapterError, "owner_unresolved"):
            self.adapter.create_role_session(
                project_id="project-test", role_id="role-review",
                parent_session_id="commander-1", plan_id="plan-test",
                snapshot_id="snapshot-test", owner_session_id="commander-2",
            )

    def test_closed_canonical_session_id_cannot_be_rebound(self) -> None:
        self.adapter.register_session(
            session_id="commander-1", project_id="project-test", role_id=None,
            parent_session_id=None, target_kind="commander", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-1",
            lease_id="lease-1", lease_expires_at="2099-01-01T00:00:00Z",
        )
        self.assertEqual(
            self.adapter.archive_session(
                "commander-1", lambda _session_id: True, actor_session_id="commander-1"
            )["result"],
            "archived",
        )
        with self.assertRaisesRegex(AdapterError, "session_id_reused"):
            self.adapter.register_session(
                session_id="commander-1", project_id="project-test", role_id=None,
                parent_session_id=None, target_kind="commander", plan_id="plan-test",
                snapshot_id="snapshot-test", owner_session_id="commander-1",
                lease_id="lease-new", lease_expires_at="2099-01-01T00:00:00Z",
            )

    def test_takeover_cannot_cross_permission_boundary(self) -> None:
        self.adapter.register_session(
            session_id="commander-1", project_id="project-test", role_id=None,
            parent_session_id=None, target_kind="commander", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-1",
            lease_id="lease-1", lease_expires_at="2099-01-01T00:00:00Z",
            permission_boundary="project-admin",
        )
        candidate = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review", parent_session_id="commander-1",
            plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
            permission_boundary="project-admin",
        )
        self.adapter.register_session(
            session_id="role-owner", project_id="project-test", role_id="role-owner",
            parent_session_id="commander-1", target_kind="main_session", plan_id="plan-test",
            snapshot_id="snapshot-test", permission_boundary="read-only",
            owner_session_id="commander-1", lease_id="owner-lease",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        result = self.adapter.takeover_role_session(
            project_id="project-test", role_id="role-review",
            candidate_session_id=candidate["session_id"], new_owner_session_id="role-owner",
            expected_lease_id=candidate["lease_id"], authorized=True,
        )
        self.assertEqual(result["result"], "permission_boundary_mismatch")

    def _role_candidate(self) -> dict:
        self.adapter.register_session(
            session_id="commander-1",
            project_id="project-test",
            role_id=None,
            parent_session_id=None,
            target_kind="commander",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-1",
            lease_id="commander-lease-test",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        return self.adapter.create_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-1",
        )

    def test_existing_role_without_decision_is_pending(self) -> None:
        candidate = self._role_candidate()
        resolved = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
        )
        self.assertEqual(resolved["result"], "session_resolution_pending")
        self.assertEqual(resolved["candidate_session_ids"], [candidate["session_id"]])
        self.assertEqual(
            self.adapter.db.execute("SELECT count(*) FROM sessions WHERE role_id='role-review'").fetchone()[0],
            1,
        )

    def test_reuse_preserves_owner_and_epoch(self) -> None:
        candidate = self._role_candidate()
        resolved = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            decision="reuse",
            candidate_session_id=candidate["session_id"],
            owner_session_id="commander-2",
        )
        self.assertEqual(resolved["result"], "resolved")
        self.assertEqual(resolved["session_resolution"], "reuse")
        self.assertEqual(resolved["role_epoch"], 1)
        self.assertEqual(resolved["owner_session_id"], "commander-1")

    def test_takeover_requires_authorization_and_rotates_epoch(self) -> None:
        candidate = self._role_candidate()
        self.adapter.register_session(
            session_id="commander-2",
            project_id="project-test",
            role_id=None,
            parent_session_id=None,
            target_kind="commander",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-2",
            lease_id="commander-lease-2",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        denied = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-2",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            decision="takeover",
            candidate_session_id=candidate["session_id"],
            owner_session_id="commander-2",
            expected_role_epoch=1,
            expected_lease_id=candidate["lease_id"],
        )
        self.assertEqual(denied["result"], "authorization_required")
        resolved = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-2",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            decision="takeover",
            candidate_session_id=candidate["session_id"],
            owner_session_id="commander-2",
            expected_role_epoch=1,
            expected_lease_id=candidate["lease_id"],
            authorized=True,
        )
        self.assertEqual(resolved["result"], "resolved")
        self.assertEqual(resolved["session_resolution"], "takeover")
        self.assertEqual(resolved["role_epoch"], 2)
        self.assertEqual(resolved["previous_owner_session_id"], "commander-1")
        self.assertTrue(resolved["handoff_receipt_id"])

    def test_session_replace_requires_checkpoint_ack_and_fences_old_owner(self) -> None:
        old = self._role_candidate()
        new = self.adapter.create_role_session(
            project_id="project-test",
            role_id="role-review",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-1",
        )
        capabilities = {
            "resolve_project", "resolve_role_session", "create_role_session",
            "record_handoff", "fence_session", "reconcile_attempt",
            "send_checkpoint", "wake_session", "recover_project",
            "create_session",
        }
        check = self.adapter.preflight(
            project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
            target_kind="main_session", canonical_target_id=old["session_id"],
            available_capabilities=capabilities, checked_by="commander-1",
            operation="handoff", transport="host",
        )
        self.assertEqual(check["result"], "ready")
        prepared = self.adapter.prepare_handoff(
            project_id="project-test", mode="session_replace",
            old_session_id=old["session_id"], new_session_id=new["session_id"],
            plan_id="plan-test", plan_revision="1", snapshot_id="snapshot-test",
            capability_check_id=check["capability_check_id"],
            authorized_actor="commander-1", expected_old_epoch=old["role_epoch"],
            expected_old_lease_id=old["lease_id"], checkpoint_ref="checkpoint-1",
        )
        self.assertEqual(prepared["result"], "prepared")
        self.assertIsNone(self.adapter.db.execute("SELECT lease_id FROM sessions WHERE session_id=?", (old["session_id"],)).fetchone()[0])
        self.assertEqual(
            self.adapter.commit_handoff(prepared["handoff_id"])["result"],
            "capability_gap",
        )
        committed = self.adapter.commit_handoff(
            prepared["handoff_id"],
            lambda session_id, handoff_id: {
                "status": "acknowledged", "host_receipt_id": "host-ack-1",
                "target_session_id": session_id, "handoff_id": handoff_id,
            },
        )
        self.assertEqual(committed["result"], "committed")
        successor = self.adapter.db.execute("SELECT lifecycle, lease_id, role_epoch FROM sessions WHERE session_id=?", (new["session_id"],)).fetchone()
        self.assertEqual(successor["lifecycle"], "active")
        self.assertTrue(successor["lease_id"])
        self.assertEqual(successor["role_epoch"], 2)
        old_row = self.adapter.db.execute("SELECT lifecycle, health_status FROM sessions WHERE session_id=?", (old["session_id"],)).fetchone()
        self.assertEqual(tuple(old_row), ("suspended", "handoff_pending"))

    def test_pending_successor_is_not_an_active_duplicate(self) -> None:
        old = self._role_candidate()
        pending = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review", parent_session_id="commander-1",
            plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
            initial_lifecycle="suspended", initial_health_status="handoff_pending",
        )
        self.assertIsNone(pending["lease_id"])
        self.assertEqual(pending["lifecycle"], "suspended")
        self.assertEqual(
            [item["session_id"] for item in self.adapter.list_role_sessions(project_id="project-test", role_id="role-review")],
            [old["session_id"]],
        )

    def test_handoff_stales_child_edges_before_old_session_archive(self) -> None:
        old = self._role_candidate()
        self.adapter.db.execute(
            "INSERT INTO child_edges(parent_session_id, child_session_id, status) VALUES (?, ?, 'open')",
            (old["session_id"], "child-open"),
        )
        self.adapter.db.commit()
        new = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review", parent_session_id="commander-1",
            plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
        )
        caps = {
            "resolve_project", "resolve_role_session", "create_role_session", "record_handoff",
            "fence_session", "reconcile_attempt", "send_checkpoint", "wake_session",
            "recover_project", "create_session",
        }
        check = self.adapter.preflight(
            project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
            target_kind="main_session", canonical_target_id=old["session_id"],
            available_capabilities=caps, checked_by="commander-1", operation="handoff", transport="host",
        )
        prepared = self.adapter.prepare_handoff(
            project_id="project-test", mode="session_replace", old_session_id=old["session_id"],
            new_session_id=new["session_id"], plan_id="plan-test", plan_revision="1",
            snapshot_id="snapshot-test", capability_check_id=check["capability_check_id"],
            authorized_actor="commander-1", expected_old_epoch=old["role_epoch"],
            expected_old_lease_id=old["lease_id"],
        )
        self.assertEqual(prepared["result"], "prepared")
        self.assertEqual(
            self.adapter.db.execute("SELECT status FROM child_edges WHERE parent_session_id=?", (old["session_id"],)).fetchone()[0],
            "stale",
        )
        self.assertEqual(
            self.adapter.archive_session(old["session_id"], lambda _session_id: True, actor_session_id="commander-1")["result"],
            "archived",
        )

    def test_unknown_handoff_can_be_retried_after_reconciliation(self) -> None:
        old = self._role_candidate()
        new = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review", parent_session_id="commander-1",
            plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
        )
        caps = {
            "resolve_project", "resolve_role_session", "create_role_session", "record_handoff",
            "fence_session", "reconcile_attempt", "send_checkpoint", "wake_session",
            "recover_project", "create_session",
        }
        check = self.adapter.preflight(
            project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
            target_kind="main_session", canonical_target_id=old["session_id"],
            available_capabilities=caps, checked_by="commander-1", operation="handoff", transport="host",
        )
        prepared = self.adapter.prepare_handoff(
            project_id="project-test", mode="session_replace", old_session_id=old["session_id"],
            new_session_id=new["session_id"], plan_id="plan-test", plan_revision="1",
            snapshot_id="snapshot-test", capability_check_id=check["capability_check_id"],
            authorized_actor="commander-1", expected_old_epoch=old["role_epoch"],
            expected_old_lease_id=old["lease_id"],
        )
        uncertain = self.adapter.commit_handoff(
            prepared["handoff_id"],
            lambda _session_id, _handoff_id: {"status": "delivered", "host_receipt_id": "maybe"},
        )
        self.assertEqual(uncertain["result"], "unknown")
        self.assertEqual(
            self.adapter.retry_handoff(prepared["handoff_id"], authorized_actor="commander-1")["result"],
            "prepared",
        )
        committed = self.adapter.commit_handoff(
            prepared["handoff_id"],
            lambda session_id, handoff_id: {
                "status": "acknowledged", "host_receipt_id": "ack-2",
                "target_session_id": session_id, "handoff_id": handoff_id,
            },
        )
        self.assertEqual(committed["result"], "committed")

    def test_handoff_capability_gap_does_not_fence_session(self) -> None:
        old = self._role_candidate()
        new = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review",
            parent_session_id="commander-1", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-1",
        )
        check = self.adapter.preflight(
            project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
            target_kind="main_session", canonical_target_id=old["session_id"],
            available_capabilities=set(), checked_by="commander-1",
            operation="handoff", transport="host",
        )
        self.assertEqual(check["result"], "capability_gap")
        with self.assertRaisesRegex(AdapterError, "capability_gap"):
            self.adapter.prepare_handoff(
                project_id="project-test", mode="session_replace",
                old_session_id=old["session_id"], new_session_id=new["session_id"],
                plan_id="plan-test", plan_revision="1", snapshot_id="snapshot-test",
                capability_check_id=check["capability_check_id"],
                authorized_actor="commander-1",
            )
        self.assertEqual(
            self.adapter.db.execute("SELECT lease_id FROM sessions WHERE session_id=?", (old["session_id"],)).fetchone()[0],
            old["lease_id"],
        )

    def test_commander_replace_cas_binds_successor_and_suspends_subordinates(self) -> None:
        self.adapter.resolve_project(
            project_id="project-test", plan_id="plan-test", plan_revision="7",
            snapshot_id="snapshot-test", commander_session_id="commander-old",
            commander_epoch="opaque-epoch-old", commander_lease_id="commander-lease-old",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        subordinate = self.adapter.create_role_session(
            project_id="project-test", role_id="role-review", parent_session_id="commander-old",
            plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-old",
        )
        successor = self.adapter.register_session(
            session_id="commander-new", project_id="project-test", role_id="",
            parent_session_id=None, target_kind="commander", plan_id="plan-test",
            snapshot_id="snapshot-test", owner_session_id="commander-new",
            lease_id="commander-lease-initial",
        )
        capabilities = {
            "resolve_project", "create_role_session", "create_session", "record_handoff", "fence_session",
            "reconcile_attempt", "send_checkpoint", "wake_session", "recover_project",
        }
        check = self.adapter.preflight(
            project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
            target_kind="commander", canonical_target_id="commander-old",
            available_capabilities=capabilities, checked_by="commander-old",
            operation="handoff", transport="host",
        )
        self.assertEqual(check["result"], "ready")
        prepared = self.adapter.prepare_handoff(
            project_id="project-test", mode="commander_replace",
            old_session_id="commander-old", new_session_id=successor["session_id"],
            plan_id="plan-test", plan_revision="7", snapshot_id="snapshot-test",
            capability_check_id=check["capability_check_id"], authorized_actor="commander-old",
            expected_old_epoch="opaque-epoch-old", expected_old_lease_id="commander-lease-old",
            checkpoint_ref="commander-checkpoint",
        )
        self.assertEqual(prepared["result"], "prepared")
        self.assertIsNone(self.adapter.db.execute(
            "SELECT lease_id FROM sessions WHERE session_id='commander-old'"
        ).fetchone()[0])
        self.assertEqual(self.adapter.db.execute(
            "SELECT lifecycle FROM sessions WHERE session_id=?", (subordinate["session_id"],)
        ).fetchone()[0], "suspended")

        # A retry after the process committed prepare must return the same
        # durable receipt even though the old lease has already been fenced.
        retried = self.adapter.prepare_handoff(
            project_id="project-test", mode="commander_replace",
            old_session_id="commander-old", new_session_id="commander-new",
            plan_id="plan-test", plan_revision="7", snapshot_id="snapshot-test",
            capability_check_id=check["capability_check_id"], authorized_actor="commander-old",
            expected_old_epoch="opaque-epoch-old", expected_old_lease_id="commander-lease-old",
        )
        self.assertEqual(retried["result"], "prepared")
        self.assertEqual(retried["handoff_id"], prepared["handoff_id"])
        self.assertEqual(self.adapter.commit_handoff(prepared["handoff_id"])["result"], "capability_gap")
        project = self.adapter.db.execute(
            "SELECT commander_session_id, commander_epoch, commander_lease_id FROM projects WHERE project_id='project-test'"
        ).fetchone()
        self.assertEqual(tuple(project), ("commander-old", "opaque-epoch-old", "commander-lease-old"))

        committed = self.adapter.commit_handoff(
            prepared["handoff_id"],
            lambda session_id, handoff_id: {
                "status": "acknowledged", "ack_ref": "host-commander-ack",
                "target_session_id": session_id, "handoff_id": handoff_id,
            },
        )
        self.assertEqual(committed["result"], "committed")
        project = self.adapter.db.execute(
            "SELECT commander_session_id, commander_epoch, commander_lease_id FROM projects WHERE project_id='project-test'"
        ).fetchone()
        self.assertEqual(project["commander_session_id"], "commander-new")
        self.assertNotEqual(project["commander_epoch"], "opaque-epoch-old")
        self.assertEqual(project["commander_lease_id"], prepared["new_lease_id"])
        new_row = self.adapter.db.execute(
            "SELECT lifecycle, lease_id FROM sessions WHERE session_id='commander-new'"
        ).fetchone()
        self.assertEqual(new_row["lifecycle"], "active")
        self.assertEqual(new_row["lease_id"], prepared["new_lease_id"])
        self.assertEqual(self.adapter.db.execute(
            "SELECT lifecycle FROM sessions WHERE session_id=?", (subordinate["session_id"],)
        ).fetchone()[0], "suspended")

    def test_no_candidate_allows_automatic_new_and_explicit_new_duplicates(self) -> None:
        self._role_candidate()
        created = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-build",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
        )
        self.assertEqual(created["result"], "resolved")
        self.assertEqual(created["session_resolution"], "new")
        second = self.adapter.resolve_role_session(
            project_id="project-test",
            role_id="role-build",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            decision="new",
        )
        self.assertEqual(second["result"], "resolved")
        self.assertEqual(second["session_resolution"], "new")
        self.assertNotEqual(created["session_id"], second["session_id"])

    def test_callback_from_superseded_role_epoch_is_stale(self) -> None:
        self._role_candidate_parent = self._role_candidate()
        self.adapter.register_session(
            session_id="commander-2",
            project_id="project-test",
            role_id=None,
            parent_session_id=None,
            target_kind="commander",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            owner_session_id="commander-2",
            lease_id="commander-lease-2",
            lease_expires_at="2099-01-01T00:00:00Z",
        )
        candidate = self.adapter.create_role_session(
            project_id="project-test",
            role_id="role-build",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            session_id="role-build-1",
        )
        packet = packet_template("role-build-1")
        packet.update(
            {
                "task_id": "task-role-epoch",
                "attempt_id": "attempt-role-epoch",
                "idempotency_key": "project-test/task-role-epoch/attempt-role-epoch",
                "target_kind": "main_session",
                "role_id": "role-build",
                "session_resolution": "reuse",
                "candidate_session_ids": ["role-build-1"],
                "lease_id": candidate["lease_id"],
            }
        )
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="main_session",
            canonical_target_id="role-build-1",
            available_capabilities={
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
            },
            checked_by="commander-1",
        )
        packet["capability_check_id"] = check["capability_check_id"]
        self.assertEqual(self.adapter.dispatch(packet, check["capability_check_id"])["result"], "dispatched")
        takeover = self.adapter.takeover_role_session(
            project_id="project-test",
            role_id="role-build",
            candidate_session_id="role-build-1",
            new_owner_session_id="commander-2",
            expected_role_epoch=1,
            expected_lease_id=candidate["lease_id"],
            authorized=True,
        )
        self.assertEqual(takeover["result"], "resolved")
        self.assertEqual(self.adapter.record_event(event_template(packet, "task.started", 1))["result"], "stale")

    def test_source_authenticator_is_checked_after_id_binding(self) -> None:
        isolated = HostAdapter(
            Path(self.temp.name) / "authenticated.sqlite",
            session_authenticator=lambda row, emitter: emitter == "trusted-child",
        )
        try:
            packet = packet_template("untrusted-child")
            packet["task_id"] = "task-auth"
            packet["attempt_id"] = "attempt-auth"
            packet["idempotency_key"] = "project-test/task-auth/attempt-auth"
            check = isolated.preflight(
                project_id=packet["project_id"],
                plan_id=packet["plan_id"],
                snapshot_id=packet["snapshot_id"],
                target_kind="internal_child",
                canonical_target_id=packet["target_session_id"],
                available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
                checked_by=packet["parent_session_id"],
            )
            packet["capability_check_id"] = check["capability_check_id"]
            isolated.dispatch(packet, check["capability_check_id"])
            with self.assertRaisesRegex(AdapterError, "source_authentication"):
                isolated.record_event(event_template(packet, "task.started", 1))
        finally:
            isolated.close()

    def test_independent_validator_can_close_claim_with_validation_receipt(self) -> None:
        self._role_candidate_parent = self._role_candidate()
        validator = self.adapter.create_role_session(
            project_id="project-test",
            role_id="role-acceptance",
            parent_session_id="commander-1",
            plan_id="plan-test",
            snapshot_id="snapshot-test",
            session_id="validator-1",
        )
        packet = packet_template("child-independent-validation")
        packet.update(
            {
                "task_id": "task-independent-validation",
                "attempt_id": "attempt-independent-validation",
                "idempotency_key": "project-test/task-independent-validation/attempt-independent-validation",
                "acceptance_mode": "independent_validator",
                "acceptance_authority_session_id": validator["session_id"],
                "acceptance_scope_id": "acceptance-scope-independent",
            }
        )
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        self.adapter.dispatch(packet, check["capability_check_id"])
        self.adapter.record_event(event_template(packet, "task.started", 1))
        claim = event_template(packet, "task.completed_claim", 2)
        self.adapter.record_event(claim)
        accepted = event_template(packet, "task.accepted", 3)
        accepted["emitted_by_session_id"] = validator["session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = validator["session_id"]
        accepted["validation_evidence_refs"] = ["validation-report-1"]
        accepted["validation_receipt_id"] = "validation-receipt-1"
        accepted["idempotency_key"] += "/validator"
        self.assertEqual(self.adapter.record_event(accepted)["status"], "accepted")

    def test_dispatch_rejects_depth_dependency_and_commander_conflicts(self) -> None:
        packet = packet_template("child-depth")
        packet["task_id"] = "task-depth"
        packet["attempt_id"] = "attempt-depth"
        packet["idempotency_key"] = "project-test/task-depth/attempt-depth"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        packet["dispatch_depth"] = 99
        with self.assertRaisesRegex(AdapterError, "dispatch_depth_exceeded"):
            self.adapter.dispatch(packet, check["capability_check_id"])
        packet["dispatch_depth"] = 1
        packet["dependency_task_ids"] = ["missing-task"]
        packet["join_policy"] = "all"
        with self.assertRaisesRegex(AdapterError, "dependency_unresolved"):
            self.adapter.dispatch(packet, check["capability_check_id"])
        base = self._packet("child-base-conflict")
        packet = packet_template("child-conflict")
        packet["task_id"] = "task-conflict"
        packet["attempt_id"] = "attempt-conflict"
        packet["idempotency_key"] = "project-test/task-conflict/attempt-conflict"
        packet["root_session_id"] = "commander-2"
        packet["parent_session_id"] = "commander-2"
        packet["callback_to"] = "commander-2"
        packet["acceptance_authority_session_id"] = "commander-2"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by="commander-2",
        )
        packet["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "commander_conflict"):
            self.adapter.dispatch(packet, check["capability_check_id"])

    def test_wake_is_idempotent_and_reconcile_reads_receipt(self) -> None:
        packet = self._packet("child-wake")
        deliveries: list[tuple[str, str]] = []
        callback = lambda session_id, receipt_id: deliveries.append((session_id, receipt_id)) or True
        self.assertEqual(self.adapter.wake_session("commander-1", "receipt-1", callback)["result"], "delivered")
        self.assertEqual(self.adapter.wake_session("commander-1", "receipt-1", callback)["result"], "duplicate")
        self.assertEqual(deliveries, [("commander-1", "receipt-1")])
        reconciliation = self.adapter.reconcile_attempt(
            project_id=packet["project_id"], task_id=packet["task_id"], attempt_id=packet["attempt_id"]
        )
        self.assertEqual(reconciliation["result"], "reconciled")
        self.assertEqual(reconciliation["state"], "dispatched")

    def test_unknown_wake_can_be_replayed_by_receipt_id(self) -> None:
        self._packet("child-wake-retry")
        outcomes = iter([False, True])
        callback = lambda session_id, receipt_id: next(outcomes)
        first = self.adapter.wake_session("commander-1", "receipt-retry", callback)
        self.assertEqual(first["result"], "unknown")
        second = self.adapter.wake_session("commander-1", "receipt-retry", callback)
        self.assertEqual(second["result"], "delivered")
        self.assertEqual(
            self.adapter.wake_session("commander-1", "receipt-retry", callback)["result"],
            "duplicate",
        )

    def test_cleanup_preflight_exposes_missing_archive_capability(self) -> None:
        packet = packet_template("child-cleanup-preflight")
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=packet["parent_session_id"],
            operation="cleanup",
        )
        self.assertEqual(check["result"], "capability_gap")
        self.assertEqual(check["missing_capabilities"], ["archive_session"])

    def test_failed_dispatch_rolls_back_project_and_commander_records(self) -> None:
        packet = packet_template("child-transaction-rollback")
        packet["task_id"] = "task-transaction-rollback"
        packet["attempt_id"] = "attempt-transaction-rollback"
        packet["idempotency_key"] = "project-test/task-transaction-rollback/attempt-transaction-rollback"
        packet["acceptance_authority_session_id"] = "missing-validator"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "acceptance_authority_unresolved"):
            self.adapter.dispatch(packet, check["capability_check_id"])
        self.assertEqual(self.adapter.db.execute("SELECT count(*) FROM projects").fetchone()[0], 0)
        self.assertEqual(self.adapter.db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
        self.assertEqual(self.adapter.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)

    def test_retry_reuses_task_identity_with_a_new_attempt_and_seals_old_attempt(self) -> None:
        packet = self._packet("child-retry", max_attempts=2)
        started = event_template(packet, "task.started", 1)
        claim = event_template(packet, "task.completed_claim", 2)
        self.adapter.record_event(started)
        self.adapter.record_event(claim)
        accepted = event_template(packet, "task.accepted", 3)
        accepted["emitted_by_session_id"] = packet["parent_session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = packet["parent_session_id"]
        accepted["validation_evidence_refs"] = ["evidence-old"]
        accepted["idempotency_key"] += "/accepted"
        self.adapter.record_event(accepted)

        retry = dict(packet)
        retry["attempt_id"] = "attempt-retry-2"
        retry["idempotency_key"] = "project-test/task-retry/attempt-retry-2"
        retry["cancel_epoch"] = "1"
        retry["lease_id"] = "lease-retry-2"
        retry["max_attempts"] = 2
        retry["task_contract_hash"] = _contract_digest(retry)
        self.assertEqual(self.adapter.dispatch(retry, retry["capability_check_id"])["result"], "dispatched")
        self.assertEqual(
            self.adapter.db.execute("SELECT count(*) FROM attempts WHERE task_id=?", (packet["task_id"],)).fetchone()[0],
            1,
        )
        late = event_template(packet, "task.progress", 4)
        self.assertEqual(self.adapter.record_event(late)["result"], "stale")
        self.assertEqual(self.adapter.record_event(event_template(retry, "task.started", 1))["result"], "accepted")

    def test_dependency_barrier_persists_waiting_then_becomes_ready(self) -> None:
        dependency = self._packet("child-dependency")
        dependent = packet_template("child-dependent")
        dependent.update(
            {
                "task_id": "task-dependent",
                "attempt_id": "attempt-dependent",
                "idempotency_key": "project-test/task-dependent/attempt-dependent",
                "dependency_task_ids": [dependency["task_id"]],
                "join_policy": "all",
            }
        )
        check = self.adapter.preflight(
            project_id=dependent["project_id"],
            plan_id=dependent["plan_id"],
            snapshot_id=dependent["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=dependent["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=dependent["parent_session_id"],
        )
        dependent["capability_check_id"] = check["capability_check_id"]
        self.adapter.dispatch(dependent, check["capability_check_id"])
        self.assertEqual(self.adapter.dependency_barrier_status(dependent["task_id"])["state"], "waiting")
        with self.assertRaisesRegex(AdapterError, "dependency_barrier_unmet"):
            self.adapter.record_event(event_template(dependent, "task.started", 1))
        self.adapter.record_event(event_template(dependency, "task.started", 1))
        claim = event_template(dependency, "task.completed_claim", 2)
        self.adapter.record_event(claim)
        accepted = event_template(dependency, "task.accepted", 3)
        accepted["emitted_by_session_id"] = dependency["parent_session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = dependency["parent_session_id"]
        accepted["validation_evidence_refs"] = ["dependency-evidence"]
        accepted["idempotency_key"] += "/accepted"
        self.adapter.record_event(accepted)
        self.assertEqual(self.adapter.dependency_barrier_status(dependent["task_id"])["state"], "ready")
        self.assertEqual(self.adapter.record_event(event_template(dependent, "task.started", 1))["result"], "accepted")

    def test_dependency_barrier_blocks_when_all_dependencies_are_blocked(self) -> None:
        dependency = self._packet("child-blocked-dependency")
        dependent = packet_template("child-blocked-dependent")
        dependent.update(
            {
                "task_id": "task-blocked-dependent",
                "attempt_id": "attempt-blocked-dependent",
                "idempotency_key": "project-test/task-blocked-dependent/attempt-blocked-dependent",
                "dependency_task_ids": [dependency["task_id"]],
                "join_policy": "all",
            }
        )
        check = self.adapter.preflight(
            project_id=dependent["project_id"],
            plan_id=dependent["plan_id"],
            snapshot_id=dependent["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=dependent["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=dependent["parent_session_id"],
        )
        dependent["capability_check_id"] = check["capability_check_id"]
        self.adapter.dispatch(dependent, check["capability_check_id"])
        self.adapter.record_event(event_template(dependency, "task.started", 1))
        self.adapter.record_event(event_template(dependency, "task.blocked", 2))
        self.assertEqual(self.adapter.dependency_barrier_status(dependent["task_id"])["state"], "blocked")
        with self.assertRaisesRegex(AdapterError, "dependency_barrier_unmet"):
            self.adapter.record_event(event_template(dependent, "task.started", 1))

    def test_impossible_bounded_partial_policy_is_rejected(self) -> None:
        dependency = self._packet("child-policy-dependency")
        dependent = packet_template("child-policy-dependent")
        dependent.update(
            {
                "task_id": "task-policy-dependent",
                "attempt_id": "attempt-policy-dependent",
                "idempotency_key": "project-test/task-policy-dependent/attempt-policy-dependent",
                "dependency_task_ids": [dependency["task_id"]],
                "join_policy": {"mode": "bounded_partial", "min_accepted": 2},
            }
        )
        check = self.adapter.preflight(
            project_id=dependent["project_id"],
            plan_id=dependent["plan_id"],
            snapshot_id=dependent["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=dependent["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=dependent["parent_session_id"],
        )
        dependent["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "join_policy_invalid"):
            self.adapter.dispatch(dependent, check["capability_check_id"])

    def test_idempotency_collisions_are_rejected_across_tasks(self) -> None:
        first = self._packet("child-idempotency-first")
        second = packet_template("child-idempotency-second")
        second.update(
            {
                "task_id": "task-idempotency-second",
                "attempt_id": "attempt-idempotency-second",
                "idempotency_key": first["idempotency_key"],
            }
        )
        check = self.adapter.preflight(
            project_id=second["project_id"],
            plan_id=second["plan_id"],
            snapshot_id=second["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=second["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=second["parent_session_id"],
        )
        second["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "idempotency_key_conflict"):
            self.adapter.dispatch(second, check["capability_check_id"])
        self.adapter.record_event(event_template(first, "task.started", 1))
        collision = event_template(first, "task.progress", 2)
        collision["task_id"] = "task-other"
        collision["attempt_id"] = "attempt-other"
        collision["idempotency_key"] = event_template(first, "task.started", 1)["idempotency_key"]
        with self.assertRaisesRegex(AdapterError, "idempotency_key_conflict"):
            self.adapter.record_event(collision)

    def test_coordination_profile_bounds_fanout(self) -> None:
        first = packet_template("child-fanout-first")
        first.update(
            {
                "task_id": "task-fanout-first",
                "attempt_id": "attempt-fanout-first",
                "idempotency_key": "project-test/task-fanout-first/attempt-fanout-first",
                "coordination_profile": {
                    "pattern": "fan_out",
                    "sop_id": "",
                    "sop_step": "",
                    "fanout_group_id": "group-test",
                    "max_fanout": 1,
                    "route_key": "",
                    "handoff_target_session_id": "",
                    "termination_conditions": ["accepted", "blocked", "failed", "unknown"],
                },
            }
        )
        check = self.adapter.preflight(
            project_id=first["project_id"],
            plan_id=first["plan_id"],
            snapshot_id=first["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=first["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=first["parent_session_id"],
        )
        first["capability_check_id"] = check["capability_check_id"]
        self.adapter.dispatch(first, check["capability_check_id"])
        second = packet_template("child-fanout-second")
        second.update(
            {
                "task_id": "task-fanout-second",
                "attempt_id": "attempt-fanout-second",
                "idempotency_key": "project-test/task-fanout-second/attempt-fanout-second",
                "coordination_profile": first["coordination_profile"],
            }
        )
        check = self.adapter.preflight(
            project_id=second["project_id"],
            plan_id=second["plan_id"],
            snapshot_id=second["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=second["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=second["parent_session_id"],
        )
        second["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "fanout_limit_exceeded"):
            self.adapter.dispatch(second, check["capability_check_id"])

        # max_fanout limits active work, so a later wave can start after the
        # first task reaches a terminal state.
        self.adapter.record_event(event_template(first, "task.started", 1))
        claim = event_template(first, "task.completed_claim", 2)
        self.adapter.record_event(claim)
        # A claim still occupies the slot until the acceptance decision.
        with self.assertRaisesRegex(AdapterError, "fanout_limit_exceeded"):
            self.adapter.dispatch(second, check["capability_check_id"])
        accepted = event_template(first, "task.accepted", 3)
        accepted["emitted_by_session_id"] = first["parent_session_id"]
        accepted["accepted_for_event_id"] = claim["event_id"]
        accepted["validated_by_session_id"] = first["parent_session_id"]
        accepted["validation_evidence_refs"] = ["fanout-wave-1"]
        accepted["idempotency_key"] += "/accepted"
        self.assertEqual(self.adapter.record_event(accepted)["result"], "accepted")
        self.assertEqual(self.adapter.dispatch(second, check["capability_check_id"])["result"], "dispatched")

    def test_dispatch_to_host_requires_transport_capability(self) -> None:
        packet = packet_template("child-transport-gap")
        packet["task_id"] = "task-transport-gap"
        packet["attempt_id"] = "attempt-transport-gap"
        packet["idempotency_key"] = "project-test/task-transport-gap/attempt-transport-gap"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind=packet["target_kind"],
            canonical_target_id=packet["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=packet["parent_session_id"],
            transport="host",
        )
        self.assertEqual(check["transport"], "host")
        packet["capability_check_id"] = check["capability_check_id"]
        result = self.adapter.dispatch_to_host(packet, check["capability_check_id"], lambda _packet: True)
        self.assertEqual(result["result"], "capability_gap")
        self.assertIn("send_task", result["missing"])
        self.assertEqual(self.adapter.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)

    def test_dispatch_to_host_records_delivery_and_seals_unknown_send(self) -> None:
        delivered = packet_template("child-transport-delivered")
        delivered.update(
            {
                "task_id": "task-transport-delivered",
                "attempt_id": "attempt-transport-delivered",
                "idempotency_key": "project-test/task-transport-delivered/attempt-transport-delivered",
            }
        )
        capabilities = {
            "create_local_child",
            "record_local_child_result",
            "record_capability_check",
            "dependency_barrier_status",
            "send_task",
        }
        check = self.adapter.preflight(
            project_id=delivered["project_id"],
            plan_id=delivered["plan_id"],
            snapshot_id=delivered["snapshot_id"],
            target_kind=delivered["target_kind"],
            canonical_target_id=delivered["target_session_id"],
            available_capabilities=capabilities,
            checked_by=delivered["parent_session_id"],
            transport="host",
        )
        self.assertEqual(check["transport"], "host")
        self.assertEqual(self.adapter.dispatch(delivered, check["capability_check_id"])["result"], "dispatched")
        self.assertEqual(
            self.adapter.dispatch_to_host(
                delivered,
                check["capability_check_id"],
                lambda packet: {
                    "status": "delivered",
                    "host_receipt_id": f"host-{packet['task_id']}",
                    "target_session_id": packet["target_session_id"],
                    "attempt_id": packet["attempt_id"],
                },
            )["result"],
            "delivered",
        )
        row = self.adapter.db.execute(
            "SELECT status, host_receipt_id FROM dispatch_deliveries WHERE task_id=?",
            (delivered["task_id"],),
        ).fetchone()
        self.assertEqual((row["status"], row["host_receipt_id"]), ("delivered", "host-task-transport-delivered"))
        self.assertEqual(
            self.adapter.reconcile_attempt(
                project_id=delivered["project_id"],
                task_id=delivered["task_id"],
                attempt_id=delivered["attempt_id"],
            )["dispatch_delivery"]["status"],
            "delivered",
        )

        unknown = packet_template("child-transport-unknown")
        unknown.update(
            {
                "task_id": "task-transport-unknown",
                "attempt_id": "attempt-transport-unknown",
                "idempotency_key": "project-test/task-transport-unknown/attempt-transport-unknown",
            }
        )
        check = self.adapter.preflight(
            project_id=unknown["project_id"],
            plan_id=unknown["plan_id"],
            snapshot_id=unknown["snapshot_id"],
            target_kind=unknown["target_kind"],
            canonical_target_id=unknown["target_session_id"],
            available_capabilities=capabilities,
            checked_by=unknown["parent_session_id"],
            transport="host",
        )
        result = self.adapter.dispatch_to_host(unknown, check["capability_check_id"], lambda _packet: False)
        self.assertEqual(result["result"], "unknown")
        self.assertEqual(
            self.adapter.db.execute("SELECT state FROM tasks WHERE task_id=?", (unknown["task_id"],)).fetchone()[0],
            "unknown",
        )
        self.assertEqual(
            self.adapter.reconcile_attempt(
                project_id=unknown["project_id"],
                task_id=unknown["task_id"],
                attempt_id=unknown["attempt_id"],
            )["dispatch_delivery"]["status"],
            "unknown",
        )

        mismatched = packet_template("child-transport-mismatch")
        mismatched.update(
            {
                "task_id": "task-transport-mismatch",
                "attempt_id": "attempt-transport-mismatch",
                "idempotency_key": "project-test/task-transport-mismatch/attempt-transport-mismatch",
            }
        )
        check = self.adapter.preflight(
            project_id=mismatched["project_id"],
            plan_id=mismatched["plan_id"],
            snapshot_id=mismatched["snapshot_id"],
            target_kind=mismatched["target_kind"],
            canonical_target_id=mismatched["target_session_id"],
            available_capabilities=capabilities,
            checked_by=mismatched["parent_session_id"],
            transport="host",
        )
        self.assertEqual(
            self.adapter.dispatch_to_host(
                mismatched,
                check["capability_check_id"],
                lambda _packet: {
                    "status": "delivered",
                    "host_receipt_id": "host-mismatch",
                    "target_session_id": "wrong-target",
                    "attempt_id": mismatched["attempt_id"],
                },
            )["result"],
            "unknown",
        )

    def test_legacy_schema_two_packet_gets_sequential_profile(self) -> None:
        packet = packet_template("child-legacy-profile")
        packet.pop("coordination_profile")
        packet["task_id"] = "task-legacy-profile"
        packet["attempt_id"] = "attempt-legacy-profile"
        packet["idempotency_key"] = "project-test/task-legacy-profile/attempt-legacy-profile"
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind="internal_child",
            canonical_target_id=packet["target_session_id"],
            available_capabilities={
                "create_local_child",
                "record_local_child_result",
                "record_capability_check",
                "dependency_barrier_status",
            },
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        packet["task_contract_hash"] = _contract_digest(_with_default_coordination_profile(packet))
        self.assertEqual(self.adapter.dispatch(packet, check["capability_check_id"])["result"], "dispatched")
        self.assertEqual(
            self.adapter.db.execute("SELECT json_extract(packet_json, '$.coordination_profile.pattern') FROM tasks WHERE task_id=?", (packet["task_id"],)).fetchone()[0],
            "sequential",
        )

    def test_receipt_sequence_counter_is_shared_across_adapter_connections(self) -> None:
        other = HostAdapter(Path(self.temp.name) / "receipts.sqlite")
        try:
            first = self._packet("child-counter-a")
            packet = packet_template("child-counter-b")
            packet.update(
                {
                    "task_id": "task-counter-b",
                    "attempt_id": "attempt-counter-b",
                    "idempotency_key": "project-test/task-counter-b/attempt-counter-b",
                }
            )
            check = other.preflight(
                project_id=packet["project_id"],
                plan_id=packet["plan_id"],
                snapshot_id=packet["snapshot_id"],
                target_kind="internal_child",
                canonical_target_id=packet["target_session_id"],
                available_capabilities={
                    "create_local_child",
                    "record_local_child_result",
                    "record_capability_check",
                    "dependency_barrier_status",
                },
                checked_by=packet["parent_session_id"],
            )
            packet["capability_check_id"] = check["capability_check_id"]
            other.dispatch(packet, check["capability_check_id"])
            sequences = [row[0] for row in self.adapter.db.execute("SELECT receipt_sequence FROM events ORDER BY receipt_sequence")]
            self.assertEqual(len(sequences), len(set(sequences)))
            self.assertGreaterEqual(len(sequences), 2)
            self.assertNotEqual(first["task_id"], packet["task_id"])
        finally:
            other.close()

    def test_task_contract_hash_is_verified(self) -> None:
        packet = packet_template("child-contract-integrity")
        packet.update(
            {
                "task_id": "task-contract-integrity",
                "attempt_id": "attempt-contract-integrity",
                "idempotency_key": "project-test/task-contract-integrity/attempt-contract-integrity",
            }
        )
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind=packet["target_kind"],
            canonical_target_id=packet["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        packet["task_contract_hash"] = "sha256:forged"
        with self.assertRaisesRegex(AdapterError, "task_contract_hash_mismatch"):
            self.adapter.dispatch(packet, check["capability_check_id"])

    def test_plan_revision_and_dependency_context_are_bound(self) -> None:
        dependency = self._packet("child-plan-boundary")
        stale = packet_template("child-plan-stale")
        stale.update(
            {
                "task_id": "task-plan-stale",
                "attempt_id": "attempt-plan-stale",
                "idempotency_key": "project-test/task-plan-stale/attempt-plan-stale",
                "plan_revision": "999",
            }
        )
        check = self.adapter.preflight(
            project_id=stale["project_id"],
            plan_id=stale["plan_id"],
            snapshot_id=stale["snapshot_id"],
            target_kind=stale["target_kind"],
            canonical_target_id=stale["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=stale["parent_session_id"],
        )
        stale["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "plan_drift"):
            self.adapter.dispatch(stale, check["capability_check_id"])

        dependent = packet_template("child-dependency-context")
        dependent.update(
            {
                "task_id": "task-dependency-context",
                "attempt_id": "attempt-dependency-context",
                "idempotency_key": "project-test/task-dependency-context/attempt-dependency-context",
                "dependency_task_ids": [dependency["task_id"]],
                "join_policy": "all",
                "snapshot_hash": "sha256:wrong-context",
            }
        )
        check = self.adapter.preflight(
            project_id=dependent["project_id"],
            plan_id=dependent["plan_id"],
            snapshot_id=dependent["snapshot_id"],
            target_kind=dependent["target_kind"],
            canonical_target_id=dependent["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=dependent["parent_session_id"],
        )
        dependent["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "dependency_context_mismatch"):
            self.adapter.dispatch(dependent, check["capability_check_id"])

    def test_child_permission_cannot_expand_parent_boundary(self) -> None:
        packet = packet_template("child-permission-expansion")
        packet.update(
            {
                "task_id": "task-permission-expansion",
                "attempt_id": "attempt-permission-expansion",
                "idempotency_key": "project-test/task-permission-expansion/attempt-permission-expansion",
                "permission_boundary": "admin",
            }
        )
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind=packet["target_kind"],
            canonical_target_id=packet["target_session_id"],
            available_capabilities={"create_local_child", "record_local_child_result", "record_capability_check", "dependency_barrier_status"},
            checked_by=packet["parent_session_id"],
        )
        packet["capability_check_id"] = check["capability_check_id"]
        with self.assertRaisesRegex(AdapterError, "permission_boundary_escalation"):
            self.adapter.dispatch(packet, check["capability_check_id"])

    def test_parent_cancellation_wakes_parent_and_seals_attempt(self) -> None:
        packet = self._packet("child-parent-cancel")
        cancelled = event_template(packet, "task.cancelled", 1)
        cancelled["emitted_by_session_id"] = packet["parent_session_id"]
        cancelled["idempotency_key"] += "/parent"
        result = self.adapter.record_event(cancelled, lambda session_id, receipt_id: session_id == packet["parent_session_id"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["wake"]["result"], "delivered")
        self.assertEqual(
            self.adapter.db.execute("SELECT state FROM tasks WHERE task_id=?", (packet["task_id"],)).fetchone()[0],
            "cancelled",
        )
        self.assertEqual(
            self.adapter.db.execute("SELECT status FROM wake_deliveries WHERE receipt_id=?", (cancelled["event_id"],)).fetchone()[0],
            "delivered",
        )

    def test_worker_cannot_seal_attempt_as_unknown(self) -> None:
        packet = self._packet("child-worker-unknown")
        with self.assertRaisesRegex(AdapterError, "source_authentication"):
            self.adapter.record_event(event_template(packet, "task.unknown", 1))

    def test_expired_target_lease_cannot_emit_callback(self) -> None:
        packet = self._packet("child-expired-lease")
        self.adapter.db.execute(
            "UPDATE sessions SET lease_expires_at='2000-01-01T00:00:00Z' WHERE session_id=?",
            (packet["target_session_id"],),
        )
        self.adapter.db.commit()
        with self.assertRaisesRegex(AdapterError, "lease_expired"):
            self.adapter.record_event(event_template(packet, "task.started", 1))

    def test_pending_host_delivery_is_sealed_without_resend(self) -> None:
        packet = packet_template("child-pending-delivery")
        packet.update(
            {
                "task_id": "task-pending-delivery",
                "attempt_id": "attempt-pending-delivery",
                "idempotency_key": "project-test/task-pending-delivery/attempt-pending-delivery",
            }
        )
        capabilities = {
            "create_local_child",
            "record_local_child_result",
            "record_capability_check",
            "dependency_barrier_status",
            "send_task",
        }
        check = self.adapter.preflight(
            project_id=packet["project_id"],
            plan_id=packet["plan_id"],
            snapshot_id=packet["snapshot_id"],
            target_kind=packet["target_kind"],
            canonical_target_id=packet["target_session_id"],
            available_capabilities=capabilities,
            checked_by=packet["parent_session_id"],
            transport="host",
        )
        packet["capability_check_id"] = check["capability_check_id"]
        self.adapter.dispatch(packet, check["capability_check_id"])
        receipt_id = f"{packet['task_id']}/{packet['attempt_id']}/dispatch"
        self.adapter.db.execute(
            "INSERT INTO dispatch_deliveries (delivery_receipt_id, task_id, attempt_id, target_session_id, status, host_receipt_id, delivery_attempt, created_at) VALUES (?, ?, ?, ?, 'pending', '', 1, ?)",
            (receipt_id, packet["task_id"], packet["attempt_id"], packet["target_session_id"], 1),
        )
        self.adapter.db.commit()
        called = []
        result = self.adapter.dispatch_to_host(packet, check["capability_check_id"], lambda _packet: called.append(True))
        self.assertEqual(result["result"], "unknown")
        self.assertEqual(called, [])
        self.assertEqual(
            self.adapter.db.execute("SELECT state FROM tasks WHERE task_id=?", (packet["task_id"],)).fetchone()[0],
            "unknown",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
