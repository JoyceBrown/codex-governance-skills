"""Bounded live smoke check for the local Codex app-server contract.

This intentionally exercises a separate ``codex app-server --stdio`` child.
It verifies native RPC method/parameter shapes and ephemeral thread behavior;
it does not claim that the child is the desktop app's shared endpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from app_server_bridge import AppServerError, CodexAppServerBridge


def _thread_ids(result: Any) -> list[str]:
    if isinstance(result, dict):
        items = result.get("threads") or result.get("data") or result.get("items") or []
    elif isinstance(result, list):
        items = result
    else:
        return []
    if not isinstance(items, list):
        return []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("id") or item.get("threadId")
        if value:
            ids.append(str(value))
    return ids


def run_smoke(*, executable: str = "codex", cwd: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    bridge: CodexAppServerBridge | None = None
    steps: list[dict[str, Any]] = []
    thread_id: str | None = None
    archive: dict[str, Any] | None = None
    try:
        bridge = CodexAppServerBridge.local(executable=executable, cwd=cwd, timeout=timeout)
        steps.append({"step": "initialize", "result": "ready"})
        started = bridge.start_task_session(cwd=cwd)
        thread = started.get("thread")
        if not isinstance(thread, dict) or not thread.get("id"):
            return {"result": "capability_gap", "missing": ["canonical_thread_id"], "steps": steps}
        thread_id = str(thread["id"])
        if thread.get("ephemeral") is False:
            return {"result": "contract_mismatch", "reason": "thread/start did not honor ephemeral=true", "steps": steps}
        steps.append({"step": "thread/start", "result": "ready", "thread_id": thread_id, "ephemeral": thread.get("ephemeral")})

        listed = bridge.list_threads()
        listed_ids = _thread_ids(listed)
        steps.append({"step": "thread/list", "result": "ready", "thread_visible": thread_id in listed_ids, "listed_count": len(listed_ids)})
        if thread_id in listed_ids:
            return {"result": "contract_mismatch", "reason": "ephemeral thread appeared in thread/list", "steps": steps}

        packet = {
            "task_id": "live-smoke-task",
            "attempt_id": "live-smoke-attempt",
            "target_session_id": thread_id,
            "objective": "Smoke protocol only: reply READY without using tools.",
        }
        sent = bridge.send_task(thread_id, packet)
        if sent.get("status") != "delivered":
            return {"result": "unknown", "reason": "turn/start did not return a turn receipt", "steps": steps, "send": sent}
        steps.append({"step": "turn/start", "result": "delivered", "turn_id": sent.get("turn_id")})

        # The live model may load configured MCP servers before answering.
        # Keep this contract check bounded: if no terminal event arrives in a
        # short grace window, request an interrupt and validate the resulting
        # terminal notification instead of burning the full smoke timeout.
        deadline = time.monotonic() + min(timeout, 12.0)
        observations = []
        while time.monotonic() < deadline:
            # An empty notification ledger is the transient state right after
            # turn/start, not a contract failure: keep polling to the deadline
            # instead of aborting on the first read.
            try:
                observations = bridge.read_task_turns(thread_id)
            except AppServerError as exc:
                if "ephemeral_turn_history_unavailable" not in str(exc):
                    raise
                time.sleep(0.2)
                continue
            if any(item.terminal for item in observations):
                break
            time.sleep(0.2)
        if not any(item.terminal for item in observations):
            turn_id = sent.get("turn_id")
            if not turn_id:
                return {"result": "unknown", "reason": "missing turn id for bounded interrupt", "steps": steps}
            interrupt = bridge.interrupt_turn(thread_id, str(turn_id))
            steps.append({"step": "turn/interrupt", "result": interrupt.get("result")})
            deadline = time.monotonic() + min(timeout, 12.0)
            while time.monotonic() < deadline:
                observations = bridge.read_task_turns(thread_id)
                if any(item.terminal for item in observations):
                    break
                time.sleep(0.2)
        terminal = next((item for item in observations if item.terminal), None)
        if terminal is None:
            return {"result": "unknown", "reason": "no terminal turn notification before timeout", "steps": steps}
        if terminal.task_packet is None:
            return {"result": "contract_mismatch", "reason": "notification stream lost the PAO task packet", "steps": steps}
        steps.append({"step": "turn/completed", "result": terminal.status, "turn_id": terminal.turn_id, "task_packet": True})
        archive = bridge.archive_session(thread_id, ephemeral=True)
        if archive.get("result") not in {"archived", "closed"}:
            return {"result": "unknown", "reason": "thread/archive was not confirmed", "steps": steps, "archive": archive}
        steps.append({"step": "thread/archive", "result": archive.get("result")})
        return {
            "result": "passed",
            "reason": "",
            "steps": steps,
        }
    except (AppServerError, OSError, FileNotFoundError) as exc:
        return {"result": "capability_gap", "error": str(exc), "steps": steps}
    finally:
        if thread_id and bridge is not None and archive is None:
            try:
                bridge.archive_session(thread_id, ephemeral=True)
            except Exception:
                pass
        if bridge is not None:
            bridge.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default="codex")
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    receipt = run_smoke(executable=args.executable, cwd=args.cwd, timeout=args.timeout)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.get("result") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
