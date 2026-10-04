from __future__ import annotations

import queue
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import Any, Mapping

from app_server_bridge import (
    AppServerError,
    CodexAppServerBridge,
    BridgeSupervisor,
    DesktopHostSnapshot,
    HostReceipt,
    LiveHostAdapter,
    StdioJsonRpcTransport,
    _resolve_process_command,
    probe_desktop_host,
)
from host_adapter import DISPATCH_CAPABILITIES, HANDOFF_CAPABILITIES, HostAdapter, event_template, packet_template


class FakeTransport:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self.responses = iter(responses or [])
        self.closed = False

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((method, dict(params or {})))
        return next(self.responses)

    def close(self) -> None:
        self.closed = True


class EphemeralReadTransport(FakeTransport):
    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((method, dict(params or {})))
        if method == "thread/read":
            raise AppServerError("thread/read: -32600: ephemeral threads do not support includeTurns")
        return {}


class EphemeralArchiveTransport(FakeTransport):
    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((method, dict(params or {})))
        if method == "thread/archive":
            raise AppServerError("thread/archive: -32600: no rollout found for thread id ephemeral-thread")
        return {}


class ReconnectableTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.reconnect_calls = 0

    def reconnect(self) -> None:
        self.reconnect_calls += 1


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def send_task(self, session_id: str, packet: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(("task", (session_id, dict(packet))))
        return {"status": "delivered", "host_receipt_id": "host-task", "target_session_id": session_id}

    def send_checkpoint(self, session_id: str, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(("checkpoint", (session_id, dict(checkpoint))))
        return {"status": "acknowledged", "host_receipt_id": "host-checkpoint", "target_session_id": session_id}

    def archive_session(self, session_id: str, *, ephemeral: bool = False) -> dict[str, Any]:
        self.calls.append(("archive", session_id))
        return {"result": "archived", "session_id": session_id}

    def start_session(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("start", kwargs))
        return {"thread": {"id": "thread-created", "ephemeral": False}}

    def start_task_session(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("start_task", kwargs))
        return {"thread": {"id": "task-thread-created", "ephemeral": True}}

    def read_task_turns(self, session_id: str) -> list[dict[str, Any]]:
        self.calls.append(("read", session_id))
        return []

    def send_wake(self, session_id: str, receipt_id: str) -> dict[str, Any]:
        self.calls.append(("wake", (session_id, receipt_id)))
        return {"status": "acknowledged", "host_receipt_id": "host-wake", "target_session_id": session_id}


class FakeState:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def dispatch_to_host(self, packet: dict[str, Any], capability_check_id: str, callback: Any) -> dict[str, Any]:
        self.calls.append(("dispatch", callback(packet)))
        return {"result": "dispatched"}

    def create_role_session(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create", kwargs))
        return {"result": "resolved", "session_id": kwargs["session_id"]}

    def record_event(self, event: dict[str, Any], wake_callback: Any = None) -> dict[str, Any]:
        self.calls.append(("event", (event, wake_callback)))
        return {"result": "accepted", "event_id": event["event_id"]}


class SupervisorBridge:
    def __init__(self) -> None:
        self.reconnect_calls = 0
        self.close_calls = 0

    def reconnect(self) -> None:
        self.reconnect_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class SupervisorLive:
    def __init__(self, results: list[list[dict[str, Any]]] | None = None, error_once: bool = False, discovered: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self.results = iter(results or [[]])
        self.error_once = error_once
        self.discovered = discovered or []

    def active_session_ids(self) -> list[str]:
        return list(self.discovered)

    def ingest_thread_results(self, session_id: str, *, wake: bool = True) -> list[dict[str, Any]]:
        self.calls.append(session_id)
        if self.error_once:
            self.error_once = False
            raise AppServerError("transport_closed")
        return next(self.results, [])


class AppServerBridgeTests(unittest.TestCase):
    def test_windows_native_executable_is_preferred_over_cmd_shim(self) -> None:
        def which(value: str) -> str | None:
            return {
                "codex.exe": r"C:\OpenAI\Codex\codex.exe",
                "codex": r"C:\Tools\npm\codex.cmd",
            }.get(value)

        with patch("app_server_bridge.shutil.which", side_effect=which):
            command = _resolve_process_command("codex", ("app-server", "--stdio"), platform_name="nt")

        self.assertEqual(command, [r"C:\OpenAI\Codex\codex.exe", "app-server", "--stdio"])

    def test_windows_cmd_shim_is_started_through_comspec(self) -> None:
        shim = r"C:\Program Files\Codex\codex.cmd"
        with (
            patch("app_server_bridge.shutil.which", return_value=shim),
            patch.dict("app_server_bridge.os.environ", {"COMSPEC": r"C:\Windows\System32\cmd.exe"}, clear=False),
        ):
            command = _resolve_process_command("codex", ("app-server", "--stdio"), platform_name="nt")

        expected_comspec = r"C:\Windows\System32\cmd.exe"
        self.assertEqual(command, f'{expected_comspec} /d /s /c ""{shim}" app-server --stdio"')

    def test_windows_explicit_bat_path_with_spaces_keeps_arguments(self) -> None:
        shim = r"C:\Program Files\Codex\codex.bat"
        with (
            patch("app_server_bridge.shutil.which", return_value=None),
            patch.dict("app_server_bridge.os.environ", {}, clear=True),
        ):
            command = _resolve_process_command(shim, ("app-server", "--stdio"), platform_name="nt")

        self.assertEqual(command, f'cmd.exe /d /s /c ""{shim}" app-server --stdio"')

    def test_non_windows_command_is_unchanged(self) -> None:
        self.assertEqual(
            _resolve_process_command("codex", ("app-server", "--stdio"), platform_name="posix"),
            ["codex", "app-server", "--stdio"],
        )

    def test_desktop_probe_rejects_private_stdio_and_unrelated_ipc(self) -> None:
        receipt = probe_desktop_host(
            DesktopHostSnapshot(
                local_transport="stdio",
                durable_transport="websocket",
                durable_authenticated=False,
                ipc_endpoints=("codex-ipc",),
            )
        )
        self.assertEqual(receipt["result"], "capability_gap")
        self.assertIn("shared_app_server_endpoint", receipt["missing"])
        self.assertIn("codex-ipc", receipt["ignored_endpoints"])
        self.assertIn("codex_ipc_is_not_app_server_json_rpc", receipt["evidence"])

    def test_desktop_probe_accepts_explicit_shared_endpoint(self) -> None:
        receipt = probe_desktop_host(
            DesktopHostSnapshot(shared_transport="websocket", shared_endpoint="ws://127.0.0.1:4317")
        )
        self.assertEqual(receipt["result"], "ready")
        self.assertEqual(receipt["endpoint"], "ws://127.0.0.1:4317")

    def test_thread_lifecycle_uses_native_methods_and_persists_by_default(self) -> None:
        fake = FakeTransport([{"thread": {"id": "thread-new"}}, {"thread": {"id": "thread-new"}}])
        bridge = CodexAppServerBridge(fake)
        started = bridge.start_session(cwd="E:/project")
        resumed = bridge.resume_session("thread-new")
        self.assertEqual(started["thread"]["id"], "thread-new")
        self.assertEqual(resumed["thread"]["id"], "thread-new")
        self.assertEqual(fake.calls[0][0], "thread/start")
        self.assertFalse(fake.calls[0][1]["ephemeral"])
        self.assertEqual(fake.calls[1], ("thread/resume", {"threadId": "thread-new"}))

    def test_task_thread_forces_ephemeral_even_when_requested_otherwise(self) -> None:
        fake = FakeTransport([{"thread": {"id": "task-thread", "ephemeral": True}}])
        bridge = CodexAppServerBridge(fake)
        started = bridge.start_task_session(cwd="E:/project", ephemeral=False)
        self.assertEqual(started["thread"]["id"], "task-thread")
        self.assertTrue(fake.calls[0][1]["ephemeral"])

    def test_task_session_is_excluded_from_long_term_discovery_and_closes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-task-session-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                bridge = FakeBridge()
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                task = live.create_task_session(
                    project_id="project-test", parent_session_id="commander-1",
                    plan_id="plan-test", snapshot_id="snapshot-test", cwd="E:/project",
                )
                self.assertTrue(task["ephemeral"])
                self.assertTrue(task["lease_id"])
                self.assertTrue(task["lease_expires_at"])
                self.assertEqual(live.active_session_ids("project-test"), ["commander-1"])
                self.assertEqual(live.active_task_session_ids("project-test"), ["task-thread-created"])
                closed = live.close_task_session("task-thread-created", actor_session_id="commander-1")
                self.assertEqual(closed["result"], "archived")
                row = state.db.execute(
                    "SELECT archived, lifecycle FROM sessions WHERE session_id=?", ("task-thread-created",)
                ).fetchone()
                self.assertEqual(tuple(row), (1, "closed"))
                self.assertIn(("archive", "task-thread-created"), bridge.calls)
            finally:
                state.close()

    def test_invalid_ephemeral_options_are_rejected_before_host_creation(self) -> None:
        bridge = FakeBridge()
        live = LiveHostAdapter(FakeState(), bridge)
        live.enable_pao()
        with self.assertRaisesRegex(AppServerError, "task_lease_duration_invalid"):
            live.create_task_session(
                project_id="project-test", parent_session_id="commander-1",
                plan_id="plan-test", snapshot_id="snapshot-test",
                lease_duration_seconds=0,
            )
        self.assertEqual([call for call in bridge.calls if call[0] == "start_task"], [])

    def test_ephemeral_recovery_closes_completed_claim_waiting_for_parent_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-ephemeral-claim-recovery-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                bridge = FakeBridge()
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                task = live.create_task_session(
                    project_id="project-test", parent_session_id="commander-1",
                    plan_id="plan-test", snapshot_id="snapshot-test",
                )
                packet = packet_template(task["session_id"])
                packet.update({
                    "task_id": "task-recovery-claim",
                    "attempt_id": "attempt-recovery-claim",
                    "idempotency_key": "project-test/task-recovery-claim/attempt-recovery-claim",
                    "lease_id": task["lease_id"],
                    "lease_expires_at": task["lease_expires_at"],
                })
                check = state.preflight(
                    project_id=packet["project_id"], plan_id=packet["plan_id"],
                    snapshot_id=packet["snapshot_id"], target_kind="internal_child",
                    canonical_target_id=packet["target_session_id"],
                    available_capabilities=set(DISPATCH_CAPABILITIES["internal_child"]),
                    checked_by="commander-1",
                )
                packet["capability_check_id"] = check["capability_check_id"]
                self.assertEqual(state.dispatch(packet, check["capability_check_id"])["result"], "dispatched")
                self.assertEqual(state.record_event(event_template(packet, "task.started", 1))["result"], "accepted")
                self.assertEqual(state.record_event(event_template(packet, "task.completed_claim", 2))["result"], "accepted")

                receipt = live.recover_ephemeral_sessions("project-test")
                self.assertEqual(receipt["pending"], [])
                self.assertEqual(receipt["closed"][0]["result"], "archived")
            finally:
                state.close()

    def test_pao_mode_defaults_off_and_disable_blocks_new_dispatch(self) -> None:
        bridge = FakeBridge()
        live = LiveHostAdapter(FakeState(), bridge)
        self.assertFalse(live.pao_mode()["pao_enabled"])
        with self.assertRaisesRegex(AppServerError, "pao_mode_disabled"):
            live.dispatch_to_host({"task_id": "task-1", "target_session_id": "thread-1"}, "check-1")
        live.enable_pao()
        self.assertTrue(live.pao_mode()["pao_enabled"])
        self.assertEqual(live.dispatch_to_host({"task_id": "task-1", "target_session_id": "thread-1"}, "check-1")["result"], "dispatched")
        live.disable_pao()
        with self.assertRaisesRegex(AppServerError, "pao_mode_disabled"):
            live.create_role_session(
                project_id="project-1", role_id="role-1", parent_session_id="commander-1",
                plan_id="plan-1", snapshot_id="snapshot-1",
            )

    def test_ephemeral_recovery_sweeps_orphans_but_preserves_live_tasks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-ephemeral-recovery-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                bridge = FakeBridge()
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                orphan = live.create_task_session(
                    project_id="project-test", parent_session_id="commander-1",
                    plan_id="plan-test", snapshot_id="snapshot-test",
                )
                receipt = live.recover_ephemeral_sessions("project-test")
                self.assertEqual(receipt["pending"], [])
                self.assertEqual(receipt["closed"][0]["result"], "archived")
                self.assertEqual(
                    state.db.execute("SELECT archived FROM sessions WHERE session_id=?", (orphan["session_id"],)).fetchone()[0],
                    1,
                )
            finally:
                state.close()

    def test_role_rotation_creates_successor_and_archives_old_thread(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-role-rotation-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                old = state.create_role_session(
                    project_id="project-test", role_id="role-review", parent_session_id="commander-1",
                    plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
                )
                bridge = FakeBridge()
                bridge.start_session = lambda **kwargs: {
                    "thread": {"id": "role-successor", "ephemeral": kwargs.get("ephemeral")}
                }
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                required = set(HANDOFF_CAPABILITIES["main_session"]) | {"create_session", "send_checkpoint"}
                check = state.preflight(
                    project_id="project-test", plan_id="plan-test", snapshot_id="snapshot-test",
                    target_kind="main_session", canonical_target_id=old["session_id"],
                    available_capabilities=required, checked_by="commander-1",
                    operation="handoff", transport="host",
                )
                result = live.replace_role_session(
                    project_id="project-test", role_id="role-review", old_session_id=old["session_id"],
                    plan_id="plan-test", plan_revision="1", snapshot_id="snapshot-test",
                    capability_check_id=check["capability_check_id"], authorized_actor="commander-1",
                    rotation_reason="test_rotation", safe_boundary=True,
                )
                self.assertEqual(result["result"], "rotated")
                self.assertEqual(result["new_session_id"], "role-successor")
                self.assertEqual(result["archive"]["result"], "archived")
                self.assertEqual(
                    state.db.execute("SELECT archived FROM sessions WHERE session_id=?", (old["session_id"],)).fetchone()[0],
                    1,
                )
            finally:
                state.close()

    def test_expired_role_recreation_skips_handoff_ack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-role-recreate-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                old = state.create_role_session(
                    project_id="project-test", role_id="role-review", parent_session_id="commander-1",
                    plan_id="plan-test", snapshot_id="snapshot-test", owner_session_id="commander-1",
                )
                bridge = FakeBridge()
                bridge.start_session = lambda **kwargs: {
                    "thread": {"id": "role-fresh", "ephemeral": kwargs.get("ephemeral")}
                }
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                mismatch = live.replace_expired_role_session(
                    project_id="project-other", role_id="role-review", old_session_id=old["session_id"],
                    parent_session_id="commander-1", plan_id="plan-test", snapshot_id="snapshot-test",
                    actor_session_id="commander-1", reason="context_expired",
                )
                self.assertEqual(mismatch["result"], "target_unresolved")
                result = live.replace_expired_role_session(
                    project_id="project-test", role_id="role-review", old_session_id=old["session_id"],
                    parent_session_id="commander-1", plan_id="plan-test", snapshot_id="snapshot-test",
                    actor_session_id="commander-1", reason="context_expired",
                )
                self.assertEqual(result["result"], "recreated")
                self.assertEqual(result["handoff"], "not_required_fresh_baseline")
                self.assertEqual(
                    [item["session_id"] for item in state.list_role_sessions(
                        project_id="project-test", role_id="role-review"
                    )],
                    ["role-fresh"],
                )
            finally:
                state.close()

    def test_fresh_commander_start_retire_and_rebinds_old_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-fresh-commander-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.resolve_project(
                    project_id="project-test", plan_id="plan-old", plan_revision="1",
                    snapshot_id="snapshot-old", commander_session_id="commander-old",
                    commander_epoch="epoch-old", commander_lease_id="lease-old",
                    lease_expires_at="2099-01-01T00:00:00Z",
                )
                bridge = FakeBridge()
                bridge.start_session = lambda **kwargs: {
                    "thread": {"id": "commander-new", "ephemeral": kwargs.get("ephemeral")}
                }
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                result = live.start_fresh_commander(
                    project_id="project-test", plan_id="plan-new", plan_revision="2",
                    snapshot_id="snapshot-new", commander_epoch="epoch-new",
                    commander_lease_id="lease-new", lease_expires_at="2099-01-01T00:00:00Z",
                )
                self.assertEqual(result["result"], "fresh_started")
                self.assertTrue(result["fresh_start"])
                self.assertIn(("archive", "commander-old"), bridge.calls)
            finally:
                state.close()

    def test_rotation_waits_for_safe_boundary_without_creating_thread(self) -> None:
        bridge = FakeBridge()
        live = LiveHostAdapter(FakeState(), bridge)
        receipt = live.rotate_role_if_needed(
            signals={"compaction_count": 2}, safe_boundary=False,
            project_id="project-test", role_id="role-review", old_session_id="old",
        )
        self.assertEqual(receipt["result"], "waiting_safe_boundary")
        self.assertEqual(bridge.calls, [])
        prepare = live.rotate_role_if_needed(signals={"compaction_count": 1}, safe_boundary=True)
        self.assertEqual(prepare["result"], "checkpoint_needed")

    def test_send_task_returns_structured_host_receipt(self) -> None:
        fake = FakeTransport([{"turn": {"id": "turn-1"}}])
        bridge = CodexAppServerBridge(fake)
        receipt = bridge.send_task("thread-1", {"task_id": "task-1", "attempt_id": "attempt-1"})
        self.assertEqual(receipt["status"], "delivered")
        self.assertEqual(receipt["target_session_id"], "thread-1")
        self.assertEqual(receipt["attempt_id"], "attempt-1")
        self.assertEqual(receipt["turn_id"], "turn-1")
        self.assertEqual(fake.calls[0][0], "turn/start")
        self.assertIn("task_id", fake.calls[0][1]["input"][0]["text"])

    def test_resolve_session_uses_canonical_thread_id(self) -> None:
        fake = FakeTransport([{"thread": {"id": "thread-1"}}])
        bridge = CodexAppServerBridge(fake)
        resolved = bridge.resolve_session("thread-1")
        self.assertEqual(resolved["result"], "resolved")
        self.assertEqual(fake.calls, [("thread/read", {"threadId": "thread-1", "includeTurns": False})])

    def test_checkpoint_and_archive_are_native_operations(self) -> None:
        fake = FakeTransport([{"turnId": "turn-checkpoint"}, {}, {}])
        bridge = CodexAppServerBridge(fake)
        checkpoint = bridge.send_checkpoint("thread-1", {"handoff_id": "handoff-1"})
        interrupted = bridge.interrupt_turn("thread-1", "turn-checkpoint")
        archived = bridge.archive_session("thread-1")
        self.assertEqual(checkpoint["status"], "delivered")
        self.assertEqual(interrupted["result"], "requested")
        self.assertEqual(archived, {"result": "archived", "session_id": "thread-1", "host": {}})
        self.assertEqual([call[0] for call in fake.calls], ["turn/start", "turn/interrupt", "thread/archive"])

    def test_empty_transport_receipts_fail_closed(self) -> None:
        bridge = CodexAppServerBridge(FakeTransport([None, None, None, None]))
        self.assertEqual(bridge.send_task("thread-1", {"task_id": "task-1"})["status"], "unknown")
        self.assertEqual(bridge.send_checkpoint("thread-1", {"handoff_id": "h"})["status"], "unknown")
        self.assertEqual(bridge.send_wake("thread-1", "r")["status"], "unknown")
        self.assertEqual(bridge.archive_session("thread-1")["result"], "unknown")

    def test_ephemeral_archive_treats_already_absent_rollout_as_closed(self) -> None:
        bridge = CodexAppServerBridge(EphemeralArchiveTransport())
        self.assertEqual(
            bridge.archive_session("ephemeral-thread", ephemeral=True)["result"],
            "closed",
        )
        with self.assertRaisesRegex(AppServerError, "no rollout found"):
            bridge.archive_session("ephemeral-thread")

    def test_archive_rejects_unconfirmed_host_status(self) -> None:
        fake = FakeTransport([{"result": "failed"}])
        bridge = CodexAppServerBridge(fake)
        with self.assertRaisesRegex(AppServerError, "archive status"):
            bridge.archive_session("thread-1")

    def test_transport_routes_concurrent_responses_by_request_id(self) -> None:
        transport = StdioJsonRpcTransport()
        first = queue.Queue()
        second = queue.Queue()
        transport._pending = {"1": first, "2": second}

        transport._route_response({"jsonrpc": "2.0", "id": "2", "result": "second"})
        transport._route_response({"jsonrpc": "2.0", "id": "1", "result": "first"})

        self.assertEqual(first.get_nowait()["result"], "first")
        self.assertEqual(second.get_nowait()["result"], "second")

    def test_bridge_reconnect_requires_transport_support(self) -> None:
        bridge = CodexAppServerBridge(FakeTransport())
        with self.assertRaisesRegex(AppServerError, "reconnect_unavailable"):
            bridge.reconnect()

    def test_bridge_reconnect_discards_ephemeral_notification_evidence(self) -> None:
        transport = ReconnectableTransport()
        bridge = CodexAppServerBridge(transport)
        bridge.handle_notification({
            "method": "turn/completed",
            "params": {
                "threadId": "old-ephemeral",
                "turn": {"id": "old-turn", "status": "completed"},
            },
        })
        bridge.reconnect()
        self.assertEqual(transport.reconnect_calls, 1)
        self.assertEqual(bridge._notification_turns, {})

    def test_bridge_close_discards_ephemeral_notification_evidence(self) -> None:
        transport = ReconnectableTransport()
        bridge = CodexAppServerBridge(transport)
        bridge.handle_notification({
            "method": "turn/completed",
            "params": {"threadId": "old-ephemeral", "turn": {"id": "old-turn", "status": "completed"}},
        })
        bridge.close()
        self.assertEqual(bridge._notification_turns, {})

    def test_local_server_start_failure_is_bounded_and_structured(self) -> None:
        with self.assertRaisesRegex(AppServerError, "app_server_unavailable: executable_not_found"):
            CodexAppServerBridge.local(executable="codex-executable-that-does-not-exist", timeout=0.2)

    def test_read_task_turns_extracts_packet_from_native_user_message(self) -> None:
        packet = packet_template("thread-1")
        turn = {
            "id": "turn-1",
            "status": "completed",
            "items": [{
                "type": "userMessage",
                "content": [{
                    "type": "text",
                    "text": "PAO task packet (authoritative receipt required):\n"
                    + json.dumps(packet, ensure_ascii=False),
                }],
            }],
        }
        fake = FakeTransport([{"thread": {"id": "thread-1", "turns": [turn]}}])
        bridge = CodexAppServerBridge(fake)
        observations = bridge.read_task_turns("thread-1")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].turn_id, "turn-1")
        self.assertEqual(observations[0].status, "completed")
        self.assertEqual(observations[0].task_packet["task_id"], packet["task_id"])

    def test_ephemeral_turn_results_use_notifications_when_thread_read_is_rejected(self) -> None:
        packet = packet_template("ephemeral-thread")
        transport = EphemeralReadTransport()
        bridge = CodexAppServerBridge(transport)
        thread_id = "ephemeral-thread"
        turn_id = "turn-ephemeral"
        bridge.handle_notification({
            "method": "turn/started",
            "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}},
        })
        bridge.handle_notification({
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "type": "userMessage",
                    "id": "user-1",
                    "content": [{
                        "type": "text",
                        "text": "PAO task packet (authoritative receipt required):\n" + json.dumps(packet),
                    }],
                },
            },
        })
        bridge.handle_notification({
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed", "items": []},
            },
        })
        observations = bridge.read_task_turns(thread_id)
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].terminal)
        self.assertEqual(observations[0].task_packet["task_id"], packet["task_id"])
        self.assertEqual(transport.calls, [("thread/read", {"threadId": thread_id, "includeTurns": True})])

    def test_notification_observer_failure_does_not_escape_or_grow_ledger(self) -> None:
        def broken_observer(_message: dict[str, Any]) -> None:
            raise RuntimeError("observer failed")

        bridge = CodexAppServerBridge(
            FakeTransport(),
            notification_handler=broken_observer,
            max_notification_threads=2,
            max_notification_turns=1,
            max_notification_items=1,
        )
        for index in range(4):
            bridge.handle_notification({
                "method": "turn/started",
                "params": {
                    "threadId": f"thread-{index}",
                    "turn": {"id": f"turn-{index}", "status": "inProgress"},
                },
            })
        self.assertGreaterEqual(len(bridge._notification_turns), 2)
        self.assertTrue(bridge._notification_callback_errors)

    def test_active_notification_turn_is_retained_with_explicit_recovery_gap(self) -> None:
        bridge = CodexAppServerBridge(FakeTransport(), max_notification_threads=1, max_notification_turns=1)
        bridge.handle_notification({
            "method": "turn/started",
            "params": {"threadId": "thread-active", "turn": {"id": "turn-1", "status": "in_progress"}},
        })
        bridge.handle_notification({
            "method": "turn/started",
            "params": {"threadId": "thread-old", "turn": {"id": "turn-old", "status": "in_progress"}},
        })
        observations = bridge._notification_observations("thread-active")
        assert observations is not None
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].recovery_gap, "active_thread_retained_over_capacity")

    def test_ephemeral_result_after_restart_is_explicit_recovery_gap(self) -> None:
        bridge = CodexAppServerBridge(EphemeralReadTransport())
        with self.assertRaisesRegex(AppServerError, "ephemeral_turn_history_unavailable"):
            bridge.read_task_turns("ephemeral-without-ledger")

    def test_live_ingest_records_started_then_completed_claim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pao-ingest-") as temp_dir:
            state = HostAdapter(Path(temp_dir) / "receipts.sqlite")
            try:
                state.register_session(
                    session_id="commander-1", project_id="project-test", role_id=None,
                    parent_session_id=None, target_kind="commander", plan_id="plan-test",
                    snapshot_id="snapshot-test", owner_session_id="commander-1",
                    lease_id="commander-lease-test", lease_expires_at="2099-01-01T00:00:00Z",
                )
                packet = packet_template("thread-1")
                packet.update({
                    "task_id": "task-ingest",
                    "attempt_id": "attempt-ingest",
                    "idempotency_key": "project-test/task-ingest/attempt-ingest",
                })
                available = set(DISPATCH_CAPABILITIES["internal_child"]) | {"send_task"}
                check = state.preflight(
                    project_id=packet["project_id"], plan_id=packet["plan_id"],
                    snapshot_id=packet["snapshot_id"], target_kind="internal_child",
                    canonical_target_id=packet["target_session_id"],
                    available_capabilities=available, checked_by="commander-1",
                    transport="host",
                )
                packet["capability_check_id"] = check["capability_check_id"]
                bridge = FakeBridge()
                bridge.send_task = lambda session_id, task: {
                    "status": "delivered", "host_receipt_id": "host-task",
                    "target_session_id": session_id,
                }
                bridge.read_task_turns = lambda session_id: [{
                    "thread_id": session_id, "turn_id": "turn-ingest", "status": "completed",
                    "error": None, "task_packet": packet,
                }]
                live = LiveHostAdapter(state, bridge)
                live.enable_pao()
                self.assertEqual(live.dispatch_to_host(packet, check["capability_check_id"])["result"], "delivered")
                results = live.ingest_thread_results("thread-1", wake=False)
                self.assertEqual([item["status"] for item in results], ["running", "completed_claim"])
                self.assertEqual(
                    state.db.execute("SELECT state FROM tasks WHERE task_id=?", ("task-ingest",)).fetchone()[0],
                    "completed_claim",
                )
                self.assertEqual(
                    state.db.execute("SELECT archived FROM sessions WHERE session_id=?", ("thread-1",)).fetchone()[0],
                    1,
                )
                self.assertIn(("archive", "thread-1"), bridge.calls)
            finally:
                state.close()

    def test_malformed_thread_result_fails_closed(self) -> None:
        fake = FakeTransport(["not-an-object"])
        bridge = CodexAppServerBridge(fake)
        with self.assertRaisesRegex(AppServerError, "non-object"):
            bridge.start_session()

    def test_host_receipt_is_serializable(self) -> None:
        self.assertEqual(
            HostReceipt("delivered", "host-1", "thread-1", "attempt-1", "turn-1").as_dict(),
            {
                "status": "delivered",
                "host_receipt_id": "host-1",
                "target_session_id": "thread-1",
                "attempt_id": "attempt-1",
                "turn_id": "turn-1",
            },
        )

    def test_live_facade_binds_native_send_and_role_creation(self) -> None:
        bridge = FakeBridge()
        state = FakeState()
        live = LiveHostAdapter(state, bridge)
        live.enable_pao()
        sent = live.dispatch_to_host({"task_id": "task-1", "target_session_id": "thread-1"}, "check-1")
        role = live.create_role_session(
            project_id="project-1", role_id="role-1", parent_session_id="commander-1",
            plan_id="plan-1", snapshot_id="snapshot-1", cwd="E:/project",
        )
        self.assertEqual(sent["result"], "dispatched")
        self.assertEqual(role["session_id"], "thread-created")
        self.assertEqual(state.calls[0][1]["target_session_id"], "thread-1")
        self.assertEqual(bridge.calls[1][0], "start")

    def test_supervisor_is_bounded_and_stops_after_idle_cycle(self) -> None:
        bridge = SupervisorBridge()
        live = SupervisorLive()
        supervisor = BridgeSupervisor(live, bridge, sleeper=lambda _: None)
        receipt = supervisor.run_bounded(["thread-1", "thread-1"], max_cycles=5, idle_cycles=1)
        self.assertEqual(receipt["result"], "stopped")
        self.assertEqual(receipt["cycles"], 1)
        self.assertEqual(live.calls, ["thread-1"])
        self.assertEqual(bridge.close_calls, 1)

    def test_supervisor_recovers_once_and_retries_the_read(self) -> None:
        bridge = SupervisorBridge()
        live = SupervisorLive(results=[[{"status": "accepted"}], []], error_once=True)
        supervisor = BridgeSupervisor(live, bridge, sleeper=lambda _: None)
        receipt = supervisor.run_once(["thread-1"])
        self.assertEqual(receipt["result"], "processed")
        self.assertEqual(bridge.reconnect_calls, 1)
        self.assertEqual(live.calls, ["thread-1", "thread-1"])

    def test_supervisor_rejects_unbounded_configuration(self) -> None:
        supervisor = BridgeSupervisor(SupervisorLive(), SupervisorBridge(), sleeper=lambda _: None)
        with self.assertRaisesRegex(ValueError, "max_cycles"):
            supervisor.run_bounded(["thread-1"], max_cycles=0)

    def test_supervisor_discovers_active_sessions_when_targets_are_omitted(self) -> None:
        bridge = SupervisorBridge()
        live = SupervisorLive(discovered=["commander-1", "role-1"])
        supervisor = BridgeSupervisor(live, bridge, sleeper=lambda _: None)
        receipt = supervisor.run_once()
        self.assertEqual(receipt["processed_sessions"], 2)
        self.assertEqual(live.calls, ["commander-1", "role-1"])

    def test_supervisor_shared_host_gate_fails_closed_before_read(self) -> None:
        bridge = SupervisorBridge()
        live = SupervisorLive(discovered=["commander-1"])
        supervisor = BridgeSupervisor(
            live,
            bridge,
            sleeper=lambda _: None,
            require_shared_host=True,
            host_snapshot=DesktopHostSnapshot(local_transport="stdio"),
        )
        receipt = supervisor.run_once()
        self.assertEqual(receipt["result"], "capability_gap")
        self.assertEqual(live.calls, [])
        self.assertIn("shared_app_server_endpoint", receipt["capability"]["missing"])


if __name__ == "__main__":
    unittest.main()
