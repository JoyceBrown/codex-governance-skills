"""Small transport bridge from PAO to the Codex app-server protocol.

The bridge owns no project truth.  It translates durable PAO operations into
real ``thread/*`` and ``turn/*`` app-server requests.  The default transport
starts a local stdio app-server with the caller's existing CODEX_HOME, which
keeps created threads in the same local Codex state store used by the desktop
runtime.  A caller can inject another JSON-RPC transport for a managed daemon
or a test double.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

try:
    from host_adapter import rotation_recommendation
except ImportError:  # pragma: no cover - package import fallback
    from .host_adapter import rotation_recommendation


class AppServerError(RuntimeError):
    """An app-server request failed or returned an invalid response."""


@dataclass(frozen=True)
class DesktopHostSnapshot:
    """Read-only facts supplied by a desktop host capability probe.

    The desktop app's private stdio child and its unrelated IPC endpoints are
    deliberately represented separately from a shareable app-server endpoint.
    This prevents a caller from treating a process name or a successful pipe
    connect as proof that PAO can control the desktop connection.
    """

    local_transport: str | None = None
    local_endpoint: str | None = None
    shared_transport: str | None = None
    shared_endpoint: str | None = None
    durable_transport: str | None = None
    durable_authenticated: bool | None = None
    ipc_endpoints: tuple[str, ...] = ()


def probe_desktop_host(snapshot: DesktopHostSnapshot) -> dict[str, Any]:
    """Return a conservative, serializable desktop host capability receipt.

    A shared endpoint must be explicitly reported by the host.  ``stdio``
    means a private child process, and ``codex-ipc`` is currently an IDE
    context channel rather than the app-server JSON-RPC transport.  Neither
    is sufficient for cross-session PAO delivery.
    """

    evidence: list[str] = []
    ignored: list[str] = []
    if snapshot.shared_endpoint and snapshot.shared_transport in {"unix", "ws", "websocket"}:
        return {
            "result": "ready",
            "transport": snapshot.shared_transport,
            "endpoint": snapshot.shared_endpoint,
            "evidence": ["host_reported_shared_app_server_endpoint"],
            "ignored_endpoints": [],
        }

    if snapshot.local_transport == "stdio":
        evidence.append("desktop_local_app_server_private_stdio")
    elif snapshot.local_transport:
        evidence.append(f"desktop_local_transport={snapshot.local_transport}")
    if snapshot.local_endpoint:
        evidence.append("desktop_local_endpoint_is_not_declared_shared")
    if snapshot.durable_transport == "websocket" and snapshot.durable_authenticated is False:
        evidence.append("durable_websocket_authentication_unavailable")
    elif snapshot.durable_transport:
        evidence.append(f"durable_transport={snapshot.durable_transport}")
    for endpoint in snapshot.ipc_endpoints:
        if endpoint == "codex-ipc":
            ignored.append(endpoint)
            evidence.append("codex_ipc_is_not_app_server_json_rpc")
        else:
            ignored.append(endpoint)

    return {
        "result": "capability_gap",
        "missing": ["shared_app_server_endpoint"],
        "evidence": evidence,
        "ignored_endpoints": ignored,
        "recovery": "inject_a_verified_shared_transport_or_use_a_separate_managed_app_server",
    }


class JsonRpcTransport(Protocol):
    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any: ...

    def close(self) -> None: ...


class StdioJsonRpcTransport:
    """Line-delimited JSON-RPC client for ``codex app-server --stdio``."""

    def __init__(
        self,
        executable: str = "codex",
        *,
        codex_home: str | os.PathLike[str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        timeout: float = 30.0,
        notification_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.executable = executable
        self.codex_home = str(codex_home) if codex_home else None
        self.cwd = str(cwd) if cwd else None
        self.timeout = timeout
        self.notification_handler = notification_handler
        self._process: subprocess.Popen[str] | None = None
        self._next_id = 0
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._reader: threading.Thread | None = None
        self._closed = False
        self._reader_errors: list[str] = []

    def start(self) -> None:
        with self._state_lock:
            if self._closed:
                raise AppServerError("transport_closed")
            if self._process is not None:
                if self._process.poll() is None:
                    return
                self._process = None
            environment = os.environ.copy()
            if self.codex_home:
                environment["CODEX_HOME"] = self.codex_home
            self._process = subprocess.Popen(
                [self.executable, "app-server", "--stdio"],
                cwd=self.cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
            )
            self._reader = threading.Thread(target=self._read_loop, name="pao-app-server-reader", daemon=True)
            self._reader.start()
            try:
                self.request(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "project-agent-orchestrator",
                            "title": "Project Agent Orchestrator",
                            "version": "0.1.0",
                        }
                    },
                )
            except Exception:
                self.close()
                raise

    def _route_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if request_id is None:
            return
        with self._pending_lock:
            waiter = self._pending.get(str(request_id))
        if waiter is not None:
            try:
                waiter.put_nowait(message)
            except queue.Full:
                pass

    def _fail_pending(self, error: dict[str, Any]) -> None:
        with self._pending_lock:
            waiters = list(self._pending.values())
        for waiter in waiters:
            try:
                waiter.put_nowait({"error": error})
            except queue.Full:
                pass

    def _record_reader_error(self, error: BaseException) -> None:
        with self._state_lock:
            self._reader_errors.append(str(error))
            del self._reader_errors[:-16]

    def _read_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._fail_pending({"code": "invalid_json", "message": str(exc)})
                    continue
                if isinstance(message, dict) and "id" in message:
                    self._route_response(message)
                elif self.notification_handler and isinstance(message, dict):
                    # A host callback is an extension point.  Its failure must
                    # never kill the transport reader and strand unrelated
                    # requests until their full timeout.
                    try:
                        self.notification_handler(message)
                    except Exception as exc:  # pragma: no cover - exercised via callback test
                        self._record_reader_error(exc)
        except Exception as exc:  # includes decoder/pipe failures
            self._record_reader_error(exc)
            self._fail_pending({"code": "transport_read_failed", "message": str(exc)})
        finally:
            self._fail_pending({"code": "transport_closed", "message": "app-server stdout closed"})
            with self._state_lock:
                if self._process is process:
                    self._process = None

    def reconnect(self) -> None:
        """Restart a dead stdio host and perform a fresh handshake."""
        with self._state_lock:
            if self._process is not None and self._process.poll() is None:
                return
            self._process = None
            self._closed = False
            self.start()

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if self._closed:
            raise AppServerError("transport_closed")
        if self._process is None:
            self.start()
        process = self._process
        if not process or not process.stdin:
            raise AppServerError("transport_not_started")
        with self._pending_lock:
            self._next_id += 1
            request_id = str(self._next_id)
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})}
        try:
            with self._write_lock:
                process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise AppServerError(f"transport_write_failed: {exc}") from exc
        deadline = time.monotonic() + self.timeout
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppServerError(f"request_timeout: {method}")
            response = waiter.get(timeout=remaining)
        except queue.Empty as exc:
            raise AppServerError(f"request_timeout: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in response:
            error = response["error"]
            raise AppServerError(f"{method}: {error.get('code')}: {error.get('message')}")
        return response.get("result")

    def close(self) -> None:
        with self._state_lock:
            self._closed = True
            process = self._process
            self._process = None
            self._fail_pending({"code": "transport_closed", "message": "transport closed"})
            if process:
                try:
                    if process.stdin:
                        process.stdin.close()
                except OSError:
                    pass
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()


@dataclass(frozen=True)
class HostReceipt:
    status: str
    host_receipt_id: str
    target_session_id: str
    attempt_id: str | None = None
    turn_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "status": self.status,
            "host_receipt_id": self.host_receipt_id,
            "target_session_id": self.target_session_id,
        }
        if self.attempt_id:
            result["attempt_id"] = self.attempt_id
        if self.turn_id:
            result["turn_id"] = self.turn_id
        return result


@dataclass(frozen=True)
class TurnObservation:
    """A bounded, replayable observation of one native Codex turn."""

    thread_id: str
    turn_id: str
    status: str
    error: Any = None
    task_packet: dict[str, Any] | None = None

    @property
    def terminal(self) -> bool:
        return str(self.status).lower() in {
            "completed", "success", "succeeded", "failed", "error",
            "interrupted", "cancelled", "canceled",
        }


class CodexAppServerBridge:
    """Map PAO host operations to native Codex app-server requests."""

    def __init__(
        self,
        transport: JsonRpcTransport,
        *,
        notification_handler: Callable[[dict[str, Any]], None] | None = None,
        max_notification_threads: int = 256,
        max_notification_turns: int = 32,
        max_notification_items: int = 128,
    ) -> None:
        for name, value in (
            ("max_notification_threads", max_notification_threads),
            ("max_notification_turns", max_notification_turns),
            ("max_notification_items", max_notification_items),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self.transport = transport
        self.notification_handler = notification_handler
        self._notification_lock = threading.RLock()
        self._notification_turns: dict[str, dict[str, dict[str, Any]]] = {}
        self._max_notification_threads = max_notification_threads
        self._max_notification_turns = max_notification_turns
        self._max_notification_items = max_notification_items
        self._notification_callback_errors: list[str] = []

    @classmethod
    def local(
        cls,
        *,
        executable: str = "codex",
        codex_home: str | os.PathLike[str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        timeout: float = 30.0,
        notification_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> "CodexAppServerBridge":
        # Bind the bridge's notification ledger before starting the process.
        # Ephemeral threads deliberately cannot be read back with
        # ``thread/read(includeTurns=true)``; their only supported result
        # channel is the live notification stream.
        transport = StdioJsonRpcTransport(
            executable,
            codex_home=codex_home,
            cwd=cwd,
            timeout=timeout,
        )
        bridge = cls(transport, notification_handler=notification_handler)
        transport.notification_handler = bridge.handle_notification
        try:
            transport.start()
        except FileNotFoundError as exc:
            transport.close()
            raise AppServerError("app_server_unavailable: executable_not_found") from exc
        except OSError as exc:
            transport.close()
            raise AppServerError(f"app_server_unavailable: {exc}") from exc
        return bridge

    def close(self) -> None:
        try:
            self.transport.close()
        finally:
            # Closing ends the only authoritative channel for ephemeral
            # notifications.  Any retained partial result must become an
            # explicit recovery gap instead of surviving a later reuse.
            with self._notification_lock:
                self._notification_turns.clear()

    def reconnect(self) -> None:
        # Ephemeral turn history exists only in the old app-server process.
        # Keeping it across a reconnect would turn stale in-memory evidence
        # into a false completion after a host restart.
        with self._notification_lock:
            self._notification_turns.clear()
        reconnect = getattr(self.transport, "reconnect", None)
        if not callable(reconnect):
            raise AppServerError("transport_reconnect_unavailable")
        reconnect()

    def list_threads(self, **filters: Any) -> dict[str, Any]:
        return self.transport.request("thread/list", filters)

    def read_thread(self, thread_id: str, *, include_turns: bool = False) -> dict[str, Any]:
        return self.transport.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})

    def read_task_turns(self, thread_id: str) -> list[TurnObservation]:
        """Read native turns and recover only PAO task packets from them.

        Plain conversation turns are ignored.  The task packet is the
        immutable identity source; response text is deliberately not copied
        into PAO events.
        """
        try:
            result = self._require_object(self.read_thread(thread_id, include_turns=True), "thread/read")
        except AppServerError as exc:
            # The live app-server rejects includeTurns for ephemeral threads.
            # Fall back only for that explicit protocol response; all other
            # failures remain visible to the bounded supervisor.
            if "ephemeral threads do not support includeTurns" not in str(exc):
                raise
            observed = self._notification_observations(thread_id)
            if observed is None:
                raise AppServerError("ephemeral_turn_history_unavailable") from exc
            return observed
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise AppServerError("thread/read returned no thread object")
        turns = thread.get("turns") or []
        if not isinstance(turns, list):
            raise AppServerError("thread/read returned invalid turns")
        observations: list[TurnObservation] = []
        for turn in turns:
            if not isinstance(turn, dict) or not turn.get("id"):
                continue
            status = turn.get("status")
            if isinstance(status, dict):
                status = status.get("type")
            observations.append(
                TurnObservation(
                    thread_id=thread_id,
                    turn_id=str(turn["id"]),
                    status=str(status or ""),
                    error=turn.get("error"),
                    task_packet=self._task_packet_from_turn(turn),
                )
            )
        return observations

    def handle_notification(self, message: dict[str, Any]) -> None:
        """Ingest app-server notifications needed for ephemeral results.

        Durable threads can be replayed from ``thread/read``.  Ephemeral
        threads are intentionally absent from the thread store, so this
        bounded in-memory ledger retains only their turn status and user
        items while the managed app-server connection is alive.  A process
        restart therefore remains an explicit recovery gap instead of being
        mistaken for success.
        """
        try:
            self._record_notification(message)
        finally:
            if self.notification_handler:
                try:
                    self.notification_handler(message)
                except Exception as exc:
                    # The ledger is authoritative for recovery; an observer
                    # callback is advisory and cannot be allowed to tear down
                    # the app-server reader thread.
                    with self._notification_lock:
                        self._notification_callback_errors.append(str(exc))
                        del self._notification_callback_errors[:-16]

    def _record_notification(self, message: Mapping[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, Mapping):
            return
        thread_id = params.get("threadId")
        if not thread_id:
            return
        thread_key = str(thread_id)
        turn = params.get("turn")
        turn_id = params.get("turnId")
        if isinstance(turn, Mapping):
            turn_id = turn.get("id") or turn_id
        if not turn_id:
            return
        turn_key = str(turn_id)
        with self._notification_lock:
            thread_turns = self._notification_turns.setdefault(thread_key, {})
            state = thread_turns.setdefault(
                turn_key,
                {
                    "thread_id": thread_key,
                    "turn_id": turn_key,
                    "status": "",
                    "error": None,
                    "items": {},
                    "last_seen": time.monotonic(),
                },
            )
            state["last_seen"] = time.monotonic()
            if method in {"turn/started", "turn/completed", "turn/failed", "turn/aborted"} and isinstance(turn, Mapping):
                status = turn.get("status")
                if isinstance(status, Mapping):
                    status = status.get("type")
                if status:
                    state["status"] = str(status)
                if "error" in turn:
                    state["error"] = turn.get("error")
                for item in turn.get("items", []) if isinstance(turn.get("items"), list) else []:
                    self._merge_notification_item(state, item)
            if method in {"item/started", "item/completed"}:
                self._merge_notification_item(state, params.get("item"))
            self._prune_notification_ledger()

    def _prune_notification_ledger(self) -> None:
        """Keep notification recovery bounded even when durable threads chat forever."""
        for turns in self._notification_turns.values():
            if len(turns) > self._max_notification_turns:
                ordered = sorted(turns, key=lambda item: float(turns[item].get("last_seen", 0)))
                for turn_id in ordered[: len(turns) - self._max_notification_turns]:
                    del turns[turn_id]
            for state in turns.values():
                items = state.get("items", {})
                if isinstance(items, dict) and len(items) > self._max_notification_items:
                    ordered_items = list(items)
                    for item_id in ordered_items[: len(items) - self._max_notification_items]:
                        del items[item_id]
        if len(self._notification_turns) > self._max_notification_threads:
            ordered_threads = sorted(
                self._notification_turns,
                key=lambda thread_id: max(
                    (float(state.get("last_seen", 0)) for state in self._notification_turns[thread_id].values()),
                    default=0,
                ),
            )
            for thread_id in ordered_threads[: len(self._notification_turns) - self._max_notification_threads]:
                del self._notification_turns[thread_id]

    @staticmethod
    def _merge_notification_item(state: dict[str, Any], item: Any) -> None:
        if not isinstance(item, Mapping):
            return
        item_id = item.get("id")
        if item_id:
            state["items"][str(item_id)] = dict(item)
        elif item.get("type") == "userMessage":
            # Some transports omit an item ID in synthetic notifications.
            state["items"][f"user-{len(state['items'])}"] = dict(item)

    def _notification_observations(self, thread_id: str) -> list[TurnObservation] | None:
        with self._notification_lock:
            turns = self._notification_turns.get(str(thread_id))
            if turns is None:
                return None
            observations: list[TurnObservation] = []
            for state in turns.values():
                synthetic = {
                    "items": list(state.get("items", {}).values()),
                }
                observations.append(
                    TurnObservation(
                        thread_id=str(thread_id),
                        turn_id=str(state["turn_id"]),
                        status=str(state.get("status") or ""),
                        error=state.get("error"),
                        task_packet=self._task_packet_from_turn(synthetic),
                    )
                )
            return observations

    def start_session(self, *, cwd: str | None = None, **options: Any) -> dict[str, Any]:
        params = dict(options)
        if cwd is not None:
            params["cwd"] = cwd
        params.setdefault("ephemeral", False)
        result = self.transport.request("thread/start", params)
        return self._require_object(result, "thread/start")

    def start_task_session(self, *, cwd: str | None = None, **options: Any) -> dict[str, Any]:
        """Start a one-shot thread whose host lifecycle is explicitly ephemeral.

        The flag is forced after copying caller options so a task caller cannot
        accidentally turn a disposable worker into a durable sidebar thread.
        """
        params = dict(options)
        params["ephemeral"] = True
        return self.start_session(cwd=cwd, **params)

    create_session = start_session

    def resolve_session(self, session_id: str) -> dict[str, Any]:
        """Resolve a canonical Codex thread without guessing from its title."""
        try:
            result = self.read_thread(session_id, include_turns=False)
        except AppServerError as exc:
            if "not found" in str(exc).lower() or "unknown" in str(exc).lower():
                return {"result": "target_unresolved", "session_id": session_id}
            raise
        return {"result": "resolved", "session_id": session_id, "thread": result}

    def resume_session(self, thread_id: str, **options: Any) -> dict[str, Any]:
        params = {"threadId": thread_id, **options}
        result = self.transport.request("thread/resume", params)
        return self._require_object(result, "thread/resume")

    def fork_session(self, thread_id: str, **options: Any) -> dict[str, Any]:
        result = self.transport.request("thread/fork", {"threadId": thread_id, **options})
        return self._require_object(result, "thread/fork")

    def send_task(
        self,
        target_session_id: str,
        task_packet: Mapping[str, Any],
        *,
        additional_context: str | None = None,
    ) -> dict[str, Any]:
        input_text = self._task_text(task_packet)
        params: dict[str, Any] = {"threadId": target_session_id, "input": [{"type": "text", "text": input_text}]}
        if additional_context:
            params["additionalContext"] = additional_context
        result = self.transport.request("turn/start", params)
        turn_id = self._turn_id(result)
        if not turn_id:
            return HostReceipt(
                status="unknown", host_receipt_id="", target_session_id=target_session_id,
                attempt_id=str(task_packet.get("attempt_id")) if task_packet.get("attempt_id") else None,
            ).as_dict()
        return HostReceipt(
            status="delivered",
            host_receipt_id=f"turn/{target_session_id}/{turn_id or uuid.uuid4().hex}",
            target_session_id=target_session_id,
            attempt_id=str(task_packet.get("attempt_id")) if task_packet.get("attempt_id") else None,
            turn_id=turn_id,
        ).as_dict()

    def send_checkpoint(self, target_session_id: str, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        result = self.transport.request(
            "turn/start",
            {
                "threadId": target_session_id,
                "input": [{"type": "text", "text": self._checkpoint_text(checkpoint)}],
            },
        )
        turn_id = self._turn_id(result)
        if not turn_id:
            return HostReceipt(
                status="unknown", host_receipt_id="", target_session_id=target_session_id,
                turn_id=None,
            ).as_dict()
        # ``turn/start`` proves that the checkpoint message was delivered to
        # the successor.  It is a true acknowledgement only when the host
        # explicitly reports one; a started turn cannot silently activate the
        # new lease.
        acknowledged = isinstance(result, dict) and (
            result.get("acknowledged") is True or result.get("status") == "acknowledged"
        )
        return HostReceipt(
            status="acknowledged" if acknowledged else "delivered",
            host_receipt_id=f"checkpoint/{target_session_id}/{turn_id or uuid.uuid4().hex}",
            target_session_id=target_session_id,
            turn_id=turn_id,
        ).as_dict()

    def send_wake(self, target_session_id: str, receipt_id: str) -> dict[str, Any]:
        result = self.transport.request(
            "turn/start",
            {
                "threadId": target_session_id,
                "input": [{
                    "type": "text",
                    "text": "PAO callback receipt acknowledgement required:\n"
                    + json.dumps({"receipt_id": receipt_id}, ensure_ascii=False, sort_keys=True),
                }],
            },
        )
        turn_id = self._turn_id(result)
        if not turn_id:
            return HostReceipt(
                status="unknown", host_receipt_id="", target_session_id=target_session_id,
            ).as_dict()
        return HostReceipt(
            status="acknowledged",
            host_receipt_id=f"wake/{target_session_id}/{receipt_id}",
            target_session_id=target_session_id,
            turn_id=turn_id,
        ).as_dict()

    def interrupt_turn(self, target_session_id: str, turn_id: str) -> dict[str, Any]:
        """Request bounded cancellation of a native turn during recovery.

        The app-server reports the eventual terminal state through
        ``turn/completed``; an interrupt response by itself is not treated as
        a task result.
        """
        result = self.transport.request(
            "turn/interrupt",
            {"threadId": target_session_id, "turnId": turn_id},
        )
        if result is None:
            return {"result": "unknown", "target_session_id": target_session_id, "turn_id": turn_id}
        if not isinstance(result, dict):
            raise AppServerError("turn/interrupt returned a non-object result")
        return {"result": "requested", "target_session_id": target_session_id, "turn_id": turn_id, "host": result}

    def archive_session(self, session_id: str, *, ephemeral: bool = False) -> dict[str, Any]:
        try:
            result = self.transport.request("thread/archive", {"threadId": session_id})
        except AppServerError as exc:
            # The live app-server removes ephemeral rollouts from its store as
            # soon as their terminal turn is closed.  In that case archive is
            # an idempotent cleanup confirmation, but only a caller that has
            # already established ``ephemeral=true`` may use this mapping.
            if ephemeral and "no rollout found" in str(exc).lower():
                return {
                    "result": "closed",
                    "session_id": session_id,
                    "reason": "ephemeral_rollout_already_absent",
                }
            raise
        if result is None:
            return {"result": "unknown", "session_id": session_id}
        if not isinstance(result, dict):
            raise AppServerError("thread/archive returned a non-object result")
        # The current local app-server acknowledges a successful archive with
        # an empty JSON object rather than a status field.
        if not result:
            return {"result": "archived", "session_id": session_id, "host": result}
        status = result.get("result") or result.get("status")
        if status not in {"archived", "closed"}:
            raise AppServerError("thread/archive returned an unconfirmed archive status")
        return {"result": status, "session_id": session_id, "host": result}

    @staticmethod
    def _require_object(result: Any, method: str) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise AppServerError(f"{method} returned a non-object result")
        return result

    @staticmethod
    def _turn_id(result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        turn = result.get("turn")
        if isinstance(turn, dict) and turn.get("id"):
            return str(turn["id"])
        if result.get("turnId"):
            return str(result["turnId"])
        return None

    @staticmethod
    def _task_text(task_packet: Mapping[str, Any]) -> str:
        return "PAO task packet (authoritative receipt required):\n" + json.dumps(
            dict(task_packet), ensure_ascii=False, sort_keys=True, indent=2
        )

    @staticmethod
    def _checkpoint_text(checkpoint: Mapping[str, Any]) -> str:
        return "PAO successor checkpoint acknowledgement required:\n" + json.dumps(
            dict(checkpoint), ensure_ascii=False, sort_keys=True, indent=2
        )

    @staticmethod
    def _task_packet_from_turn(turn: Mapping[str, Any]) -> dict[str, Any] | None:
        prefix = "PAO task packet (authoritative receipt required):"
        for item in turn.get("items", []) if isinstance(turn.get("items", []), list) else []:
            if not isinstance(item, Mapping) or item.get("type") != "userMessage":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, Mapping) or not isinstance(block.get("text"), str):
                    continue
                text = block["text"]
                if not text.startswith(prefix):
                    continue
                payload = text[len(prefix):].lstrip(" \r\n")
                try:
                    parsed = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, dict) and parsed.get("task_id") and parsed.get("attempt_id"):
                    return parsed
        return None


class LiveHostAdapter:
    """Bind a reference ``HostAdapter`` state machine to Codex threads.

    The state machine remains the source of lease and receipt truth. This
    facade only supplies the callbacks required at the real-host boundary.
    """

    def __init__(self, state_adapter: Any, bridge: CodexAppServerBridge) -> None:
        self.state = state_adapter
        self.bridge = bridge
        self._pao_enabled = False

    @classmethod
    def local(
        cls,
        state_adapter: Any,
        **bridge_options: Any,
    ) -> "LiveHostAdapter":
        """Create a live facade and start the managed app-server on demand."""
        return cls(state_adapter, CodexAppServerBridge.local(**bridge_options))

    def set_pao_mode(self, enabled: bool) -> dict[str, Any]:
        """Apply the explicit per-runtime PAO switch.

        The default is off for every new facade instance.  Turning it off
        stops new PAO creation/dispatch but leaves cleanup and in-flight
        recovery available.
        """
        if not isinstance(enabled, bool):
            raise AppServerError("pao_mode_invalid")
        self._pao_enabled = enabled
        return {"result": "mode_changed", "pao_enabled": enabled}

    def enable_pao(self) -> dict[str, Any]:
        return self.set_pao_mode(True)

    def disable_pao(self) -> dict[str, Any]:
        return self.set_pao_mode(False)

    def pao_mode(self) -> dict[str, Any]:
        return {"result": "mode", "pao_enabled": self._pao_enabled}

    def _require_pao(self) -> None:
        if not self._pao_enabled:
            raise AppServerError("pao_mode_disabled")

    def dispatch_to_host(self, packet: dict[str, Any], capability_check_id: str) -> dict[str, Any]:
        self._require_pao()
        return self.state.dispatch_to_host(
            packet,
            capability_check_id,
            lambda task: self.bridge.send_task(str(task["target_session_id"]), task),
        )

    def start_fresh_commander(
        self,
        *,
        project_id: str,
        plan_id: str,
        plan_revision: str,
        snapshot_id: str,
        commander_epoch: str,
        commander_lease_id: str,
        lease_expires_at: str | None = None,
        cwd: str | None = None,
        thread_options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a new commander after an explicit clean project restart.

        This is a fresh baseline path, not a commander handoff.  The old
        commander is retired only after the state adapter confirms that its
        tasks are terminal and the host archive succeeds.
        """
        self._require_pao()
        options = dict(thread_options or {})
        options["ephemeral"] = False
        host_thread = self.bridge.start_session(cwd=cwd, **options)
        thread = host_thread.get("thread")
        if not isinstance(thread, dict) or not thread.get("id"):
            raise AppServerError("thread/start did not return a canonical thread id")
        session_id = str(thread["id"])

        def archive_old(target_session_id: str) -> bool:
            return self.bridge.archive_session(target_session_id).get("result") in {"archived", "closed"}

        try:
            result = self.state.resolve_project(
                project_id=project_id,
                plan_id=plan_id,
                plan_revision=plan_revision,
                snapshot_id=snapshot_id,
                commander_session_id=session_id,
                commander_epoch=commander_epoch,
                commander_lease_id=commander_lease_id,
                lease_expires_at=lease_expires_at,
                fresh_start=True,
                archive_callback=archive_old,
                authorized_actor=None,
            )
        except Exception:
            try:
                self.bridge.archive_session(session_id)
            finally:
                raise
        if result.get("result") not in {"resolved", "fresh_started"}:
            self.bridge.archive_session(session_id)
            return {"result": result.get("result", "unknown"), "project": result, "host_thread": host_thread}
        result["host_thread"] = host_thread
        result["fresh_start"] = True
        return result

    def retire_role_session(
        self,
        session_id: str,
        *,
        actor_session_id: str,
        reason: str = "expired",
    ) -> dict[str, Any]:
        """Retire an expired role without checkpoint or successor ACK."""
        self._require_pao()
        return self.state.retire_role_session(
            session_id,
            lambda target: self.bridge.archive_session(target).get("result") in {"archived", "closed"},
            actor_session_id=actor_session_id,
            reason=reason,
        )

    def replace_expired_role_session(
        self,
        *,
        project_id: str,
        role_id: str,
        old_session_id: str,
        parent_session_id: str,
        plan_id: str,
        snapshot_id: str,
        actor_session_id: str,
        cwd: str | None = None,
        thread_options: Mapping[str, Any] | None = None,
        reason: str = "expired",
    ) -> dict[str, Any]:
        """Retire an expired role and create a fresh role session.

        No checkpoint is sent because this operation intentionally starts a
        new baseline after the old role has ended.
        """
        self._require_pao()
        db = getattr(self.state, "db", None)
        if db is None:
            raise AppServerError("state_session_store_unavailable")
        old = db.execute(
            "SELECT project_id, role_id, parent_session_id, target_kind, archived FROM sessions WHERE session_id=?",
            (old_session_id,),
        ).fetchone()
        if (
            not old
            or old["archived"]
            or old["target_kind"] != "main_session"
            or old["project_id"] != project_id
            or old["role_id"] != role_id
            or old["parent_session_id"] != parent_session_id
        ):
            return {"result": "target_unresolved", "old_session_id": old_session_id}
        retired = self.retire_role_session(
            old_session_id,
            actor_session_id=actor_session_id,
            reason=reason,
        )
        if retired.get("result") != "retired":
            return {"result": "retirement_" + str(retired.get("result", "unknown")), "retirement": retired}
        try:
            successor = self.create_role_session(
                project_id=project_id,
                role_id=role_id,
                parent_session_id=parent_session_id,
                plan_id=plan_id,
                snapshot_id=snapshot_id,
                owner_session_id=actor_session_id,
                cwd=cwd,
                thread_options=dict(thread_options or {}),
            )
        except Exception as exc:
            return {
                "result": "retired_creation_failed",
                "retirement": retired,
                "error": str(exc),
            }
        return {
            "result": "recreated",
            "retirement": retired,
            "successor": successor,
            "handoff": "not_required_fresh_baseline",
        }

    def active_session_ids(self, project_id: str | None = None) -> list[str]:
        """Return canonical active commander/role IDs from PAO state."""
        db = getattr(self.state, "db", None)
        if db is None:
            raise AppServerError("state_session_store_unavailable")
        clauses = [
            "archived=0",
            "lifecycle IN ('active', 'suspended')",
            "target_kind IN ('commander', 'main_session')",
            "health_status NOT IN ('handoff_pending', 'parent_handoff_pending', 'commander_handoff_pending')",
        ]
        params: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        rows = db.execute(
            "SELECT session_id FROM sessions WHERE " + " AND ".join(clauses) + " ORDER BY created_at, session_id",
            params,
        ).fetchall()
        return [str(row["session_id"]) for row in rows]

    def active_task_session_ids(self, project_id: str | None = None) -> list[str]:
        """Return active one-shot task threads only when explicitly requested."""
        db = getattr(self.state, "db", None)
        if db is None:
            raise AppServerError("state_session_store_unavailable")
        clauses = [
            "archived=0",
            "lifecycle IN ('active', 'suspended')",
            "target_kind='internal_child'",
        ]
        params: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        rows = db.execute(
            "SELECT session_id FROM sessions WHERE " + " AND ".join(clauses) + " ORDER BY created_at, session_id",
            params,
        ).fetchall()
        return [str(row["session_id"]) for row in rows]

    def ingest_thread_results(self, session_id: str, *, wake: bool = True) -> list[dict[str, Any]]:
        """Convert terminal native turns into durable PAO worker events.

        A completed turn becomes a ``completed_claim`` only. Acceptance still
        belongs to the registered parent or validator. Replaying the same
        thread is idempotent because event IDs and keys include the native
        turn ID, and terminal task projections are skipped.
        """
        results: list[dict[str, Any]] = []
        for observation in self.bridge.read_task_turns(session_id):
            packet = self._observation_field(observation, "task_packet")
            terminal = self._observation_field(observation, "terminal")
            if terminal is None:
                status = str(self._observation_field(observation, "status") or "").lower()
                terminal = status in {"completed", "success", "succeeded", "failed", "error", "interrupted", "cancelled", "canceled"}
            if not isinstance(packet, dict) or not terminal:
                continue
            recorded: list[dict[str, Any]] = []
            for event in self._events_for_observation(packet, observation):
                callback = self._wake_parent if wake else None
                receipt = self.state.record_event(event, wake_callback=callback)
                recorded.append(receipt)
                results.append(receipt)
            # A disposable host thread is closed only after its terminal
            # worker event has been durably recorded.  Acceptance remains a
            # parent responsibility and may happen after this cleanup.
            db = getattr(self.state, "db", None)
            session = db.execute(
                "SELECT target_kind, owner_session_id, parent_session_id, archived FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone() if db is not None else None
            if session and session["target_kind"] == "internal_child" and not session["archived"]:
                actor = session["owner_session_id"] or session["parent_session_id"]
                if actor:
                    cleanup = self.close_task_session(session_id, actor_session_id=str(actor))
                    if recorded and isinstance(recorded[-1], dict):
                        recorded[-1]["cleanup"] = cleanup
        return results

    def _wake_parent(self, session_id: str, receipt_id: str) -> bool:
        receipt = self.bridge.send_wake(session_id, receipt_id)
        return receipt.get("status") == "acknowledged"

    def _events_for_observation(self, packet: dict[str, Any], observation: Any) -> list[dict[str, Any]]:
        try:
            from host_adapter import TERMINAL_STATES, event_template
        except ImportError:  # pragma: no cover - package import fallback
            from .host_adapter import TERMINAL_STATES, event_template

        db = getattr(self.state, "db", None)
        if db is None:
            raise AppServerError("state_event_store_unavailable")
        task = db.execute(
            "SELECT state, last_source_sequence FROM tasks WHERE task_id=? AND attempt_id=?",
            (packet.get("task_id"), packet.get("attempt_id")),
        ).fetchone()
        if not task:
            return []
        current_state = str(task["state"])
        if current_state in TERMINAL_STATES or current_state in {"completed_claim", "partial"}:
            return []
        status = str(self._observation_field(observation, "status") or "").lower()
        if status in {"completed", "success", "succeeded"}:
            terminal_type = "task.completed_claim"
            terminal_emitter = packet["target_session_id"]
        elif status in {"failed", "error"}:
            terminal_type = "task.failed"
            terminal_emitter = packet["target_session_id"]
        elif status in {"interrupted", "cancelled", "canceled"}:
            terminal_type = "task.unknown"
            terminal_emitter = packet["parent_session_id"]
        else:
            return []
        sequence = int(task["last_source_sequence"] or 0) + 1
        events: list[dict[str, Any]] = []
        if current_state == "dispatched":
            events.append(self._host_event(event_template(packet, "task.started", sequence), observation, packet["target_session_id"]))
            sequence += 1
        elif current_state != "running":
            return []
        events.append(self._host_event(event_template(packet, terminal_type, sequence), observation, terminal_emitter))
        return events

    @staticmethod
    def _observation_field(observation: Any, name: str) -> Any:
        if isinstance(observation, Mapping):
            return observation.get(name)
        return getattr(observation, name, None)

    @staticmethod
    def _host_event(event: dict[str, Any], observation: Any, emitter: str) -> dict[str, Any]:
        turn_id = str(LiveHostAdapter._observation_field(observation, "turn_id"))
        event_type = event["event_type"]
        event["event_id"] = f"codex-turn/{turn_id}/{event_type}"
        event["idempotency_key"] = f"{event['idempotency_key']}/codex-turn/{turn_id}/{event_type}"
        event["emitted_by_session_id"] = emitter
        event["receipt_origin"] = "host_observed"
        event["observed_by"] = "codex-app-server"
        event["host_turn_id"] = turn_id
        return event

    def commit_handoff(self, handoff_id: str) -> dict[str, Any]:
        def send_checkpoint(session_id: str, receipt_id: str) -> dict[str, Any]:
            row = self.state.db.execute(
                "SELECT * FROM handoff_receipts WHERE handoff_id=?", (receipt_id,)
            ).fetchone()
            if not row:
                return {"status": "unknown", "target_session_id": session_id}
            checkpoint = {
                "handoff_id": receipt_id,
                "project_id": row["project_id"],
                "role_id": row["role_id"],
                "mode": row["mode"],
                "old_session_id": row["old_session_id"],
                "new_session_id": row["new_session_id"],
                "plan_id": row["plan_id"],
                "plan_revision": row["plan_revision"],
                "snapshot_id": row["snapshot_id"],
                "permission_boundary": row["permission_boundary"],
                "in_flight_attempt_ids": json.loads(row["in_flight_attempt_ids_json"]),
                "checkpoint_ref": row["checkpoint_ref"],
            }
            return self.bridge.send_checkpoint(session_id, checkpoint)

        return self.state.commit_handoff(handoff_id, send_checkpoint)

    def retry_handoff(self, handoff_id: str, *, authorized_actor: str) -> dict[str, Any]:
        """Retry an uncertain checkpoint once the caller has reconciled it."""
        retry = self.state.retry_handoff(handoff_id, authorized_actor=authorized_actor)
        if retry.get("result") not in {"prepared", "duplicate"}:
            return retry
        if retry.get("result") == "duplicate":
            return retry
        return self.commit_handoff(handoff_id)

    def archive_session(self, session_id: str, *, actor_session_id: str) -> dict[str, Any]:
        def archive(target_session_id: str) -> bool:
            db = getattr(self.state, "db", None)
            row = db.execute(
                "SELECT target_kind FROM sessions WHERE session_id=?",
                (target_session_id,),
            ).fetchone() if db is not None else None
            ephemeral = bool(row and row["target_kind"] == "internal_child")
            return self.bridge.archive_session(target_session_id, ephemeral=ephemeral).get("result") in {"archived", "closed"}

        return self.state.archive_session(
            session_id,
            archive,
            actor_session_id=actor_session_id,
        )

    def create_task_session(self, **kwargs: Any) -> dict[str, Any]:
        """Create and register a disposable internal task thread.

        The host thread is created first so the state store records the
        canonical ID returned by app-server.  Registration failure archives
        that thread before the error is re-raised.
        """
        self._require_pao()
        thread_options = dict(kwargs.pop("thread_options", {}))
        target_kind = kwargs.pop("target_kind", "internal_child")
        if target_kind != "internal_child":
            raise AppServerError("task_session_target_kind_invalid")
        lease_id = kwargs.pop("lease_id", None) or f"task-lease/{uuid.uuid4().hex}"
        lease_expires_at = kwargs.pop("lease_expires_at", None)
        if lease_expires_at is None:
            duration = kwargs.pop("lease_duration_seconds", 3600)
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
                raise AppServerError("task_lease_duration_invalid")
            lease_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=float(duration))
            ).isoformat().replace("+00:00", "Z")
        host_thread = self.bridge.start_task_session(
            cwd=kwargs.pop("cwd", None), **thread_options
        )
        thread = host_thread.get("thread")
        if not isinstance(thread, dict) or not thread.get("id"):
            raise AppServerError("thread/start did not return a canonical thread id")
        session_id = str(thread["id"])
        try:
            result = self.state.register_session(
                session_id=session_id,
                role_id=None,
                target_kind="internal_child",
                owner_session_id=kwargs.pop("owner_session_id", None),
                lease_id=lease_id,
                lease_expires_at=lease_expires_at,
                **kwargs,
            )
        except Exception:
            try:
                self.bridge.archive_session(session_id, ephemeral=True)
            finally:
                raise
        result.update({"host_thread": host_thread, "ephemeral": True, "target_kind": "internal_child"})
        return result

    def close_task_session(self, session_id: str, *, actor_session_id: str) -> dict[str, Any]:
        """Archive a disposable task thread and close its durable session row."""
        return self.archive_session(session_id, actor_session_id=actor_session_id)

    def recover_ephemeral_sessions(self, project_id: str | None = None) -> dict[str, Any]:
        """Boundedly reconcile disposable sessions after a process restart.

        A thread with no task or only terminal task attempts is safe to close.
        A thread with a live attempt is returned as pending for normal task
        reconciliation; this method never guesses that work was completed.
        """
        db = getattr(self.state, "db", None)
        if db is None:
            raise AppServerError("state_session_store_unavailable")
        closed: list[dict[str, Any]] = []
        pending: list[str] = []
        for session_id in self.active_task_session_ids(project_id):
            row = db.execute(
                "SELECT owner_session_id, parent_session_id FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                continue
            tasks = db.execute(
                "SELECT state FROM tasks WHERE json_extract(packet_json, '$.target_session_id')=?",
                (session_id,),
            ).fetchall()
            if any(str(task["state"]) not in {
                # A native turn has already ended once a claim/partial result
                # is durable.  Parent acceptance may still be pending, but it
                # no longer requires keeping the disposable host thread alive.
                "blocked", "failed", "cancelled", "unknown", "accepted", "rejected",
                "stale", "completed_claim", "partial",
            } for task in tasks):
                pending.append(session_id)
                continue
            actor = row["owner_session_id"] or row["parent_session_id"]
            if not actor:
                pending.append(session_id)
                continue
            closed.append(self.close_task_session(session_id, actor_session_id=str(actor)))
        return {
            "result": "reconciled",
            "closed": closed,
            "pending": pending,
        }

    def create_role_session(self, **kwargs: Any) -> dict[str, Any]:
        """Create a real Codex thread, then register its canonical ID in PAO."""
        self._require_pao()
        thread_options = dict(kwargs.pop("thread_options", {}))
        thread_options["ephemeral"] = False
        host_thread = self.bridge.start_session(
            cwd=kwargs.pop("cwd", None), **thread_options
        )
        thread = host_thread.get("thread")
        if not isinstance(thread, dict) or not thread.get("id"):
            raise AppServerError("thread/start did not return a canonical thread id")
        session_id = str(thread["id"])
        try:
            result = self.state.create_role_session(session_id=session_id, **kwargs)
        except Exception:
            try:
                self.bridge.archive_session(session_id)
            finally:
                raise
        result["host_thread"] = host_thread
        return result

    def replace_role_session(
        self,
        *,
        project_id: str,
        role_id: str,
        old_session_id: str,
        plan_id: str,
        plan_revision: str,
        snapshot_id: str,
        capability_check_id: str,
        authorized_actor: str,
        cwd: str | None = None,
        thread_options: Mapping[str, Any] | None = None,
        checkpoint_ref: str = "",
        old_status_evidence_ref: str = "",
        rotation_reason: str = "",
        expected_old_epoch: int | str | None = None,
        expected_old_lease_id: str | None = None,
        safe_boundary: bool = False,
    ) -> dict[str, Any]:
        """Rotate a durable role instance while keeping the role identity.

        ``role_id`` is the durable responsibility.  Every rotation creates a
        fresh canonical thread/session ID, fences the old lease, acknowledges
        the bounded checkpoint, and then archives the old host thread.
        """
        self._require_pao()
        if not safe_boundary:
            return {"result": "waiting_safe_boundary", "old_session_id": old_session_id}
        check = self.state.db.execute(
            "SELECT result, operation, canonical_target_id FROM capability_checks WHERE check_id=?",
            (capability_check_id,),
        ).fetchone()
        if not check or check["result"] != "ready" or check["operation"] != "handoff" or check["canonical_target_id"] != old_session_id:
            return {"result": "capability_gap", "old_session_id": old_session_id}
        old = self.state.db.execute(
            "SELECT * FROM sessions WHERE session_id=? AND project_id=? AND role_id=? AND target_kind='main_session'",
            (old_session_id, project_id, role_id),
        ).fetchone()
        if not old or old["archived"]:
            return {"result": "target_unresolved", "old_session_id": old_session_id}
        if old["parent_session_id"] is None:
            return {"result": "parent_unresolved", "old_session_id": old_session_id}

        successor: dict[str, Any] | None = None
        prepared_handoff_id: str | None = None
        try:
            successor = self.create_role_session(
                project_id=project_id,
                role_id=role_id,
                parent_session_id=old["parent_session_id"],
                plan_id=plan_id,
                snapshot_id=snapshot_id,
                owner_session_id=authorized_actor,
                permission_boundary=old["permission_boundary"],
                cwd=cwd,
                thread_options=dict(thread_options or {}),
                initial_lifecycle="suspended",
                initial_health_status="handoff_pending",
            )
            prepared = self.state.prepare_handoff(
                project_id=project_id,
                mode="session_replace",
                old_session_id=old_session_id,
                new_session_id=successor["session_id"],
                plan_id=plan_id,
                plan_revision=plan_revision,
                snapshot_id=snapshot_id,
                capability_check_id=capability_check_id,
                authorized_actor=authorized_actor,
                checkpoint_ref=checkpoint_ref,
                old_status_evidence_ref=old_status_evidence_ref,
                rotation_reason=rotation_reason,
                expected_old_epoch=expected_old_epoch,
                expected_old_lease_id=expected_old_lease_id,
            )
            if prepared.get("result") != "prepared":
                cleanup = self.archive_session(successor["session_id"], actor_session_id=authorized_actor)
                return {"result": prepared.get("result", "unknown"), "handoff": prepared, "successor": successor, "cleanup": cleanup}
            prepared_handoff_id = prepared["handoff_id"]
            handoff = self.commit_handoff(prepared_handoff_id)
            if handoff.get("result") != "committed":
                return {"result": handoff.get("result", "unknown"), "handoff": handoff, "successor": successor, "recovery": "reconcile_prepared_handoff"}
            archived = self.archive_session(old_session_id, actor_session_id=authorized_actor)
            return {
                "result": "rotated",
                "role_id": role_id,
                "old_session_id": old_session_id,
                "new_session_id": successor["session_id"],
                "handoff": handoff,
                "archive": archived,
                "cleanup": "complete" if archived.get("result") == "archived" else archived,
            }
        except Exception:
            if successor is not None and prepared_handoff_id is None:
                try:
                    self.archive_session(successor["session_id"], actor_session_id=authorized_actor)
                except Exception:
                    pass
            raise

    def rotate_role_if_needed(
        self,
        *,
        signals: Mapping[str, Any],
        safe_boundary: bool,
        **replacement: Any,
    ) -> dict[str, Any]:
        """Apply the rotation policy at a verified task or phase boundary."""
        recommendation = rotation_recommendation(**dict(signals))
        decision = recommendation["decision"]
        if decision == "continue":
            return {"result": "continued", "recommendation": recommendation}
        if decision == "prepare_rotation":
            return {"result": "checkpoint_needed", "recommendation": recommendation}
        if not safe_boundary:
            return {"result": "waiting_safe_boundary", "recommendation": recommendation}
        result = self.replace_role_session(safe_boundary=True, **replacement)
        result["recommendation"] = recommendation
        return result


class BridgeSupervisor:
    """Run bounded bridge cycles with one recovery retry at most.

    This is intentionally a pull supervisor. It does not create a background
    thread or an unbounded polling loop; callers choose a finite cycle and
    time budget, and the returned receipt records each cycle's observations.
    """

    def __init__(
        self,
        live_adapter: LiveHostAdapter,
        bridge: CodexAppServerBridge,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        require_shared_host: bool = False,
        host_snapshot: DesktopHostSnapshot | None = None,
    ) -> None:
        self.live_adapter = live_adapter
        self.bridge = bridge
        self.clock = clock
        self.sleeper = sleeper
        self.require_shared_host = require_shared_host
        self.host_snapshot = host_snapshot
        self._running = False
        self._stopped = False

    def start(self) -> dict[str, Any]:
        if self._running:
            return {"result": "duplicate", "status": "running"}
        if self.require_shared_host:
            capability = probe_desktop_host(self.host_snapshot or DesktopHostSnapshot())
            if capability["result"] != "ready":
                return {"result": "capability_gap", "capability": capability}
        if self._stopped:
            recovery = self._try_reconnect()
            if recovery["result"] != "recovered":
                return recovery
        self._running = True
        self._stopped = False
        return {"result": "started", "status": "running"}

    def recover(self) -> dict[str, Any]:
        if not self._running:
            return {"result": "not_running"}
        return self._try_reconnect()

    def run_once(self, session_ids: list[str] | tuple[str, ...] | None = None, *, wake: bool = True) -> dict[str, Any]:
        started = self.start()
        if started["result"] not in {"started", "duplicate"}:
            return started
        if session_ids is None:
            discover = getattr(self.live_adapter, "active_session_ids", None)
            if not callable(discover):
                return {"result": "capability_gap", "missing": ["active_session_ids"], "events": []}
            session_ids = discover()
        targets = list(dict.fromkeys(str(session_id) for session_id in session_ids if session_id))
        if not targets:
            return {"result": "idle", "processed_sessions": 0, "events": []}
        try:
            return self._read_targets(targets, wake=wake)
        except AppServerError as first_error:
            recovery = self.recover()
            if recovery["result"] != "recovered":
                return {
                    "result": "capability_gap",
                    "error": str(first_error),
                    "recovery": recovery,
                    "processed_sessions": 0,
                    "events": [],
                }
            # One bounded replay is safe because event IDs and task terminal
            # projections make the read idempotent.
            try:
                receipt = self._read_targets(targets, wake=wake)
            except AppServerError as second_error:
                return {
                    "result": "transport_error",
                    "error": str(second_error),
                    "recovery": recovery,
                    "processed_sessions": 0,
                    "events": [],
                }
            receipt["recovery"] = recovery
            return receipt

    def run_bounded(
        self,
        session_ids: list[str] | tuple[str, ...] | None = None,
        *,
        max_cycles: int = 1,
        max_seconds: float = 30.0,
        idle_cycles: int = 1,
        interval_seconds: float = 0.0,
        wake: bool = True,
        stop_on_exit: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(max_cycles, int) or max_cycles < 1:
            raise ValueError("max_cycles must be positive")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be positive")
        if not isinstance(idle_cycles, int) or idle_cycles < 1:
            raise ValueError("idle_cycles must be positive")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")
        started_at = self.clock()
        receipts: list[dict[str, Any]] = []
        idle_streak = 0
        try:
            started = self.start()
            if started["result"] not in {"started", "duplicate"}:
                return {"result": started["result"], "cycles": 0, "receipts": [started]}
            for cycle in range(max_cycles):
                if self.clock() - started_at >= max_seconds:
                    break
                receipt = self.run_once(session_ids, wake=wake)
                receipts.append(receipt)
                if receipt.get("result") not in {"processed", "idle"}:
                    break
                if receipt.get("events"):
                    idle_streak = 0
                else:
                    idle_streak += 1
                    if idle_streak >= idle_cycles:
                        break
                if cycle + 1 < max_cycles and interval_seconds:
                    remaining = max_seconds - (self.clock() - started_at)
                    if remaining <= 0:
                        break
                    self.sleeper(min(interval_seconds, remaining))
            return {"result": "stopped", "cycles": len(receipts), "receipts": receipts}
        finally:
            if stop_on_exit:
                self.stop()

    def stop(self) -> dict[str, Any]:
        if self._stopped:
            return {"result": "duplicate", "status": "stopped"}
        self.bridge.close()
        self._running = False
        self._stopped = True
        return {"result": "stopped", "status": "stopped"}

    def _read_targets(self, targets: list[str], *, wake: bool) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        for session_id in targets:
            events.extend(self.live_adapter.ingest_thread_results(session_id, wake=wake))
        return {"result": "processed", "processed_sessions": len(targets), "events": events}

    def _try_reconnect(self) -> dict[str, Any]:
        try:
            self.bridge.reconnect()
        except AppServerError as exc:
            return {"result": "capability_gap", "error": str(exc)}
        return {"result": "recovered", "status": "connected"}
