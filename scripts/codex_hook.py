#!/usr/bin/env python3
"""Codex lifecycle hooks for automatic durable-context recovery and guards."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import context_state


MAX_RESUME_CHARS = 3600
MAX_LOG_BYTES = 1024 * 1024
MAX_STATE_ENTRIES = 128
STATE_TTL_SECONDS = 24 * 60 * 60
RECOVERY_FAILURE_LIMIT = 2
LOCK_WAIT_SECONDS = 0.5
LOCK_STALE_SECONDS = 10.0

CHANGE_HINT = re.compile(
    r"(?:\b(?:change|modify|rename|remove|delete|add|must|instead|scope|route|acceptance|"
    r"standard|priority|phase|implement|continue)\b|"
    r"修改|改成|改为|重命名|新增|增加|删除|不要|必须|验收|标准|范围|路线|优先级|阶段|开始|继续)",
    re.IGNORECASE,
)
SHELL_CONTROL = re.compile(r"[;&|<>`\r\n]|\$\(", re.IGNORECASE)
READ_ONLY_COMMANDS = {
    "get-content", "get-childitem", "select-string", "resolve-path", "test-path",
    "measure-object", "rg",
}
LIFECYCLE_EVENTS = {"recover", "change", "repair", "reconcile", "verify", "checkpoint"}
SHELL_TOOL_NAMES = {"bash", "exec_command"}
PATCH_TARGET = re.compile(r"(?m)^\*\*\* (?:Add|Update|Delete) File:\s*(.+?)\s*$")
WRITE_TOOL_NAME = re.compile(
    r"(?:^|__|_)(?:write|edit|apply_patch|click|type|input|upload|navigate|new_tab|close|cookies_set|"
    r"evaluate|exec|mouse|mouse_drag|window_activate|window_move|window_resize|clipboard_write|"
    r"clipboard_clean|send|create|update|delete|remove|rename|install|add|computer_use)$",
    re.IGNORECASE,
)


@dataclass
class HookResult:
    payload: dict[str, Any]
    outcome: str
    reason: str
    project: tuple[Path, Path] | None


def configure_utf8_stdio() -> None:
    """Keep the JSON hook protocol stable on Windows and Unix alike."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (AttributeError, TypeError, ValueError):
            continue


def emit(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


def input_payload() -> dict[str, Any]:
    configure_utf8_stdio()
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def shell_tokens(command: str) -> list[str] | None:
    if not command.strip() or SHELL_CONTROL.search(command):
        return None
    try:
        return [token.strip('"') for token in shlex.split(command, posix=False)]
    except ValueError:
        return None


def is_read_only_shell(command: str) -> bool:
    tokens = shell_tokens(command)
    if not tokens:
        return False
    executable = Path(tokens[0]).name.casefold()
    if executable in READ_ONLY_COMMANDS:
        if executable == "rg" and any(token.casefold() in {"--pre", "--passthru"} for token in tokens[1:]):
            return False
        return True
    if executable == "git" and len(tokens) > 1:
        return tokens[1].casefold() in {"status", "diff", "log", "show", "branch"}
    if executable == "codex" and len(tokens) > 2:
        return tokens[1].casefold() == "mcp" and tokens[2].casefold() in {"list", "get"}
    return False


def resolved_path(value: str, base: Path | None = None) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and base is not None:
        candidate = base / candidate
    return candidate.resolve()


def find_project(start: str | None) -> tuple[Path, Path] | None:
    candidate = resolved_path(start or os.getcwd())
    if candidate.is_file():
        candidate = candidate.parent
    for root in (candidate, *candidate.parents):
        ledger = root / context_state.DEFAULT_DIR
        if (ledger / "manifest.json").is_file():
            manifest = context_state.read_json(ledger / "manifest.json")
            recorded_root = str(manifest.get("root") or "").strip()
            if not recorded_root:
                raise ValueError(f"ledger manifest is missing its project root: {ledger}")
            if resolved_path(recorded_root) != root.resolve():
                raise ValueError(f"ledger manifest root does not match its directory: {ledger}")
            return root, ledger
    return None


def tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def shell_command(payload: dict[str, Any]) -> str:
    values = tool_input(payload)
    tool_name = str(payload.get("tool_name") or "").casefold()
    key = "cmd" if tool_name == "exec_command" else "command"
    return str(values.get(key) or "")


def explicit_file_targets(payload: dict[str, Any]) -> list[str]:
    values = tool_input(payload)
    tool_name = str(payload.get("tool_name") or "").casefold()
    if tool_name == "apply_patch":
        patch = str(values.get("patch") or values.get("input") or "")
        return [match.strip().strip('"') for match in PATCH_TARGET.findall(patch) if match.strip()]
    if tool_name in {"edit", "write"}:
        for key in ("file_path", "path", "filename"):
            value = str(values.get(key) or "").strip()
            if value:
                return [value]
    return []


def resolve_project(payload: dict[str, Any]) -> tuple[Path, Path] | None:
    cwd = resolved_path(str(payload.get("cwd") or os.getcwd()))
    tool_name = str(payload.get("tool_name") or "").casefold()
    values = tool_input(payload)
    if str(payload.get("hook_event_name") or "") == "PreToolUse" and tool_name in SHELL_TOOL_NAMES:
        workdir = str(values.get("workdir") or "").strip()
        return find_project(str(resolved_path(workdir, cwd))) if workdir else find_project(str(cwd))

    targets = explicit_file_targets(payload)
    if not targets:
        return find_project(str(cwd))
    projects: dict[str, tuple[Path, Path]] = {}
    unowned = False
    for target in targets:
        target_parent = resolved_path(target, cwd).parent
        project = find_project(str(target_parent))
        if project is None:
            unowned = True
            continue
        projects[str(project[0]).casefold()] = project
    if len(projects) > 1 or (projects and unowned):
        raise ValueError("write targets cross durable-context project roots")
    if projects:
        return next(iter(projects.values()))
    return None


def manifest_task(ledger: Path) -> str:
    try:
        return str(context_state.read_json(ledger / "manifest.json").get("task", ""))
    except (OSError, ValueError):
        return ""


def stable_id(value: Any) -> str:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


def additional_context(event: str, value: str, system_message: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": value,
        }
    }
    if system_message:
        result["systemMessage"] = system_message
    return result


def deny_tool(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason[:1800],
        }
    }


@contextmanager
def auxiliary_lock(ledger: Path) -> Iterator[None]:
    lock_path = ledger / ".hook-state.lock"
    token = f"{os.getpid()}:{time.time_ns()}"
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(token)
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("hook auxiliary state is busy")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            if lock_path.read_text(encoding="utf-8") == token:
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def load_state_unlocked(ledger: Path) -> dict[str, Any]:
    path = ledger / "hook-state.json"
    if not path.is_file():
        return {"version": 1, "turn_guards": {}, "compactions": {}, "recovery_failures": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "turn_guards": {}, "compactions": {}, "recovery_failures": {}}
    if not isinstance(value, dict):
        return {"version": 1, "turn_guards": {}, "compactions": {}, "recovery_failures": {}}
    value.setdefault("version", 1)
    value.setdefault("turn_guards", {})
    value.setdefault("compactions", {})
    value.setdefault("recovery_failures", {})
    return value


def prune_state(state: dict[str, Any]) -> None:
    cutoff = time.time() - STATE_TTL_SECONDS
    for key in ("turn_guards", "compactions", "recovery_failures"):
        values = state.get(key)
        if not isinstance(values, dict):
            state[key] = {}
            continue
        current = {
            str(name): item
            for name, item in values.items()
            if isinstance(item, dict) and float(item.get("created_epoch", 0)) >= cutoff
        }
        ordered = sorted(current.items(), key=lambda pair: float(pair[1].get("created_epoch", 0)))
        state[key] = dict(ordered[-MAX_STATE_ENTRIES:])


def update_state(ledger: Path, mutate: Any) -> dict[str, Any]:
    with auxiliary_lock(ledger):
        state = load_state_unlocked(ledger)
        prune_state(state)
        mutate(state)
        prune_state(state)
        context_state.atomic_write(
            ledger / "hook-state.json",
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )
        return state


def read_state(ledger: Path) -> dict[str, Any]:
    try:
        with auxiliary_lock(ledger):
            state = load_state_unlocked(ledger)
            prune_state(state)
            return state
    except (OSError, TimeoutError, ValueError):
        return {"version": 1, "turn_guards": {}, "compactions": {}, "recovery_failures": {}}


def recovery_fingerprint(manifest: dict[str, Any], reasons: list[str]) -> str:
    """Hash only bounded recovery metadata; never persist raw prompts or tool input."""
    payload = {
        "task_id": stable_id(manifest.get("task_id")),
        "checkpoint": int(manifest.get("checkpoint", 0)),
        "requirements_revision": int(manifest.get("requirements_revision", 0)),
        "requirements_hash": stable_id(manifest.get("recorded_requirements_hash")),
        "reasons": sorted(set(str(reason)[:240] for reason in reasons)),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def record_recovery_failure(ledger: Path, fingerprint: str, payload: dict[str, Any]) -> int:
    count = 0

    def mutate(state: dict[str, Any]) -> None:
        nonlocal count
        failures = state.setdefault("recovery_failures", {})
        previous = failures.get(fingerprint)
        count = int(previous.get("count", 0)) + 1 if isinstance(previous, dict) else 1
        failures[fingerprint] = {
            "count": count,
            "first_epoch": float(previous.get("first_epoch", time.time())) if isinstance(previous, dict) else time.time(),
            "last_epoch": time.time(),
            "created_epoch": time.time(),
            "session": stable_id(payload.get("session_id")),
        }

    update_state(ledger, mutate)
    return count


def clear_recovery_failures(ledger: Path) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["recovery_failures"] = {}

    try:
        update_state(ledger, mutate)
    except (OSError, TimeoutError, ValueError):
        pass


def ledger_snapshot(root: Path, ledger: Path) -> dict[str, Any]:
    manifest = context_state.read_json(ledger / "manifest.json")
    return {
        "task_id": context_state.validate_task_id(manifest.get("task_id")),
        "checkpoint": int(manifest.get("checkpoint", 0)),
        "requirements_revision": int(manifest.get("requirements_revision", 0)),
        "requirements_hash": str(manifest.get("recorded_requirements_hash", "")),
        "status": str(manifest.get("status", "unknown")),
        "root_hash": stable_id(str(root.resolve())),
    }


def same_snapshot(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("task_id", "checkpoint", "requirements_revision", "requirements_hash")
    return all(left.get(key) == right.get(key) for key in keys)


def guard_key(payload: dict[str, Any]) -> str:
    turn = stable_id(payload.get("turn_id"))
    session = stable_id(payload.get("session_id"))
    return f"{session}:{turn or 'session'}"


def set_turn_guard(ledger: Path, payload: dict[str, Any], snapshot: dict[str, Any], reason: str) -> None:
    key = guard_key(payload)

    def mutate(state: dict[str, Any]) -> None:
        state["turn_guards"][key] = {
            **snapshot,
            "reason": reason,
            "created_epoch": time.time(),
        }

    update_state(ledger, mutate)


def pending_turn_guard(ledger: Path, payload: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any] | None:
    key = guard_key(payload)
    state = read_state(ledger)
    guard = state.get("turn_guards", {}).get(key)
    if not isinstance(guard, dict):
        return None
    if (
        guard.get("requirements_revision") == snapshot.get("requirements_revision")
        and guard.get("requirements_hash") == snapshot.get("requirements_hash")
    ):
        return guard

    def mutate(value: dict[str, Any]) -> None:
        value.get("turn_guards", {}).pop(key, None)

    try:
        update_state(ledger, mutate)
    except (OSError, TimeoutError, ValueError):
        pass
    return None


def store_compaction(ledger: Path, payload: dict[str, Any], snapshot: dict[str, Any]) -> None:
    key = stable_id(payload.get("session_id")) or "unknown"

    def mutate(state: dict[str, Any]) -> None:
        state["compactions"][key] = {
            **snapshot,
            "trigger": str(payload.get("trigger") or "unknown"),
            "created_epoch": time.time(),
        }

    update_state(ledger, mutate)


def compaction_snapshot(ledger: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    key = stable_id(payload.get("session_id")) or "unknown"
    value = read_state(ledger).get("compactions", {}).get(key)
    return value if isinstance(value, dict) else None


def clear_compaction(ledger: Path, payload: dict[str, Any]) -> None:
    key = stable_id(payload.get("session_id")) or "unknown"

    def mutate(state: dict[str, Any]) -> None:
        state.get("compactions", {}).pop(key, None)

    try:
        update_state(ledger, mutate)
    except (OSError, TimeoutError, ValueError):
        pass


def tool_is_write_capable(payload: dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool_name") or "")
    if tool_name in {"apply_patch", "Edit", "Write"}:
        return True
    if tool_name.casefold() not in SHELL_TOOL_NAMES:
        return bool(WRITE_TOOL_NAME.search(tool_name))
    return not is_read_only_shell(shell_command(payload))


def is_lifecycle_repair(payload: dict[str, Any], root: Path, ledger: Path) -> bool:
    if str(payload.get("tool_name") or "").casefold() not in SHELL_TOOL_NAMES:
        return False
    tokens = shell_tokens(shell_command(payload))
    if not tokens:
        return False
    index = 0
    executable = Path(tokens[index]).name.casefold()
    if executable in {"py", "py.exe"}:
        if len(tokens) < 3 or tokens[1] not in {"-3", "-3.11", "-3.12", "-3.13"}:
            return False
        index = 2
    elif executable in {"python", "python.exe", "python3", "python3.exe"}:
        index = 1
    else:
        return False
    if index >= len(tokens):
        return False
    try:
        script = Path(tokens[index]).expanduser().resolve()
        trusted = Path(context_state.__file__).resolve()
    except OSError:
        return False
    if script != trusted:
        return False
    tokens = tokens[index + 1 :]
    option_index = 0
    while option_index < len(tokens) and tokens[option_index].startswith("--"):
        option = tokens[option_index].casefold()
        if option not in {"--root", "--dir"} or option_index + 1 >= len(tokens):
            return False
        value = tokens[option_index + 1]
        if option == "--root":
            try:
                if Path(value).expanduser().resolve() != root.resolve():
                    return False
            except OSError:
                return False
        elif Path(value).as_posix().strip("/").casefold() != ledger.name.casefold():
            return False
        option_index += 2
    tokens = tokens[option_index:]
    if not tokens or tokens[0].casefold() != "auto":
        return False
    event = ""
    for position, token in enumerate(tokens[1:], start=1):
        if token == "--event" and position + 1 < len(tokens):
            event = tokens[position + 1].casefold()
            break
    return event in LIFECYCLE_EVENTS


def handle_session_start(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    try:
        if (ledger / ".transaction.json").is_file():
            context_state.automatic(
                root, ledger, "recover", manifest_task(ledger), "", "", "", "", "active", MAX_RESUME_CHARS
            )
        result = context_state.automatic(
            root, ledger, "start", manifest_task(ledger), "", "", "", "", "active", MAX_RESUME_CHARS
        )
        if result.get("action") == "blocked":
            try:
                context_state.automatic(
                    root, ledger, "repair", "", "", "", "", "", "active", MAX_RESUME_CHARS
                )
                result = context_state.automatic(
                    root, ledger, "start", manifest_task(ledger), "", "", "", "", "active", MAX_RESUME_CHARS
                )
            except (OSError, ValueError) as exc:
                result["repair_error"] = str(exc)[:600]
        brief = str(result.get("resume", "")).strip()
        gate_closed = result.get("action") == "blocked"
        reason = "resume_blocked" if gate_closed else "resume_verified"
        source = str(payload.get("source") or "")
        if source == "compact":
            before = compaction_snapshot(ledger, payload)
            after = ledger_snapshot(root, ledger)
            if before is None:
                reason = "compact_pre_state_missing"
                brief = (
                    "Durable-context compaction warning: no pre-compaction snapshot was found; "
                    "the current ledger was independently validated.\n\n" + brief
                )
            elif not same_snapshot(before, after):
                reason = "compact_state_mismatch"
                brief = (
                    "Durable-context compaction warning: the task metadata changed across compaction. "
                    "Reconcile the ledger before editing.\n\n" + brief
                )
            else:
                reason = "compact_state_match"
            clear_compaction(ledger, payload)
        if gate_closed:
            # Compaction metadata matching does not re-authorize a stale project.
            reason = "resume_blocked"
        output = additional_context(
            "SessionStart",
            brief,
            "Durable-context recovery gate is closed; only trusted metadata was restored."
            if reason == "resume_blocked"
            else "",
        ) if brief else {}
        return HookResult(output, "warning" if reason == "resume_blocked" else "allow", reason, (root, ledger))
    except Exception as exc:
        warning = (
            "Durable-context warning: automatic resume was not completed. "
            f"Re-check the project ledger before relying on prior context. ({exc})"
        )
        return HookResult(
            additional_context("SessionStart", warning, "Durable-context resume failed"),
            "warning",
            "resume_failed",
            (root, ledger),
        )


def handle_user_prompt(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    prompt = str(payload.get("prompt") or "")
    if not CHANGE_HINT.search(prompt):
        return HookResult({}, "allow", "no_requirement_hint", (root, ledger))
    errors = context_state.verify(ledger, expected_root=root)
    if errors:
        message = "The durable-context ledger is invalid. Reconcile it before changing project state."
        return HookResult(
            additional_context("UserPromptSubmit", message, "Durable-context ledger needs repair"),
            "warning",
            "invalid_ledger",
            (root, ledger),
        )
    snapshot = ledger_snapshot(root, ledger)
    set_turn_guard(ledger, payload, snapshot, "requirement_hint")
    message = (
        "This prompt may change the objective, scope, route, acceptance standard, or an implementation detail. "
        "Compare it with the current requirements and record one requirement revision before any project write. "
        "Do not ask the user to manage the ledger."
    )
    return HookResult(additional_context("UserPromptSubmit", message), "guarded", "requirement_hint", (root, ledger))


def handle_pre_tool(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    if not tool_is_write_capable(payload):
        return HookResult({}, "allow", "read_only_tool", (root, ledger))
    if is_lifecycle_repair(payload, root, ledger):
        return HookResult({}, "allow", "lifecycle_repair", (root, ledger))
    errors = context_state.verify(ledger, expected_root=root)
    if errors:
        reason = "Durable-context rejected this write because the project ledger is invalid: " + "; ".join(errors)
        return HookResult(deny_tool(reason), "deny", "invalid_ledger", (root, ledger))
    consistency = context_state.reconcile(ledger, expected_root=root)
    if consistency.get("blocking"):
        reasons = list(dict.fromkeys(
            [str(item) for item in consistency.get("errors", [])]
            + [str(item) for item in consistency.get("blocking_warnings", [])]
        ))
        reason = (
            "Durable-context rejected this write because recovery is blocked by current-state drift. "
            "Inspect the files and record a trusted checkpoint/rebaseline first: "
            + "; ".join(reasons)
        )
        return HookResult(deny_tool(reason), "deny", "recovery_gate", (root, ledger))
    snapshot = ledger_snapshot(root, ledger)
    guard = pending_turn_guard(ledger, payload, snapshot)
    if guard is not None:
        reason = (
            "Durable-context rejected this write because the current prompt may change project requirements, "
            "but the ledger revision/hash has not changed yet. Record the requirement change through the "
            "automatic lifecycle, then retry the write."
        )
        return HookResult(deny_tool(reason), "deny", "requirement_revision_pending", (root, ledger))
    return HookResult({}, "allow", "ledger_valid", (root, ledger))


def handle_pre_compact(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    errors = context_state.verify(ledger, expected_root=root)
    if errors:
        reason = "Durable-context stopped compaction because the ledger is invalid: " + "; ".join(errors)
        return HookResult(
            {"continue": False, "stopReason": reason[:1800], "systemMessage": "Compaction needs ledger repair"},
            "deny",
            "invalid_ledger",
            (root, ledger),
        )
    snapshot = ledger_snapshot(root, ledger)
    guard = pending_turn_guard(ledger, payload, snapshot)
    if guard is not None:
        reason = "Record the pending requirement revision before compacting this task."
        return HookResult(
            {"continue": False, "stopReason": reason, "systemMessage": "Compaction paused for durable context"},
            "deny",
            "requirement_revision_pending",
            (root, ledger),
        )
    store_compaction(ledger, payload, snapshot)
    return HookResult({}, "allow", "pre_compact_snapshot_saved", (root, ledger))


def handle_post_compact(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    errors = context_state.verify(ledger, expected_root=root)
    if errors:
        return HookResult(
            {"systemMessage": "Durable-context detected an invalid ledger after compaction; repair it before editing."},
            "warning",
            "invalid_ledger",
            (root, ledger),
        )
    before = compaction_snapshot(ledger, payload)
    after = ledger_snapshot(root, ledger)
    if before is None:
        return HookResult(
            {"systemMessage": "Durable-context could not find the pre-compaction snapshot; SessionStart will revalidate."},
            "warning",
            "compact_pre_state_missing",
            (root, ledger),
        )
    if not same_snapshot(before, after):
        return HookResult(
            {"systemMessage": "Durable-context metadata changed across compaction; reconcile before editing."},
            "warning",
            "compact_state_mismatch",
            (root, ledger),
        )
    return HookResult({}, "allow", "compact_state_match", (root, ledger))


def handle_stop(payload: dict[str, Any], root: Path, ledger: Path) -> HookResult:
    if bool(payload.get("stop_hook_active")):
        return HookResult({}, "allow", "continuation_already_used", (root, ledger))
    try:
        manifest = context_state.read_json(ledger / "manifest.json")
        reasons: list[str] = []
        if (ledger / ".transaction.json").is_file():
            reasons.append("an incomplete ledger transaction needs recovery")
        consistency = context_state.reconcile(ledger, expected_root=root)
        reasons.extend(str(item) for item in consistency.get("errors", []))
        reasons.extend(str(item) for item in consistency.get("warnings", []))
        try:
            snapshot = ledger_snapshot(root, ledger)
            if pending_turn_guard(ledger, payload, snapshot) is not None:
                reasons.append("the current prompt may contain an unrecorded requirement change")
        except (OSError, ValueError):
            pass
        if manifest.get("status") == "complete" and not reasons:
            clear_recovery_failures(ledger)
            return HookResult({}, "allow", "complete_clean", (root, ledger))
        if not reasons:
            clear_recovery_failures(ledger)
            return HookResult({}, "allow", "active_clean", (root, ledger))
        fingerprint = recovery_fingerprint(manifest, reasons)
        attempt = record_recovery_failure(ledger, fingerprint, payload)
        if attempt >= RECOVERY_FAILURE_LIMIT:
            message = (
                "Durable-context recovery is still blocked for the same verified failure state. "
                "Automatic continuation is disabled and this turn may stop safely. "
                "Run the trusted lifecycle repair event after inspecting the reported ledger state."
            )
            return HookResult(
                {"systemMessage": message},
                "warning",
                "recovery_circuit_open",
                (root, ledger),
            )
        reason = (
            "Before stopping, preserve the durable task state: "
            + "; ".join(dict.fromkeys(reasons))
            + ". Run the trusted repair/recovery lifecycle, then continue once."
        )
        return HookResult({"decision": "block", "reason": reason[:2000]}, "continue", "dirty_ledger", (root, ledger))
    except Exception as exc:
        return HookResult(
            {"systemMessage": f"Durable-context Stop hook warning: {exc}"},
            "warning",
            "stop_check_failed",
            (root, ledger),
        )


def dispatch(payload: dict[str, Any]) -> HookResult:
    event = str(payload.get("hook_event_name") or "").strip()
    project = resolve_project(payload)
    if not project:
        return HookResult({}, "allow", "no_ledger", None)
    root, ledger = project
    if event == "SessionStart":
        return handle_session_start(payload, root, ledger)
    if event == "UserPromptSubmit":
        return handle_user_prompt(payload, root, ledger)
    if event == "PreToolUse":
        return handle_pre_tool(payload, root, ledger)
    if event == "PreCompact":
        return handle_pre_compact(payload, root, ledger)
    if event == "PostCompact":
        return handle_post_compact(payload, root, ledger)
    if event == "Stop":
        return handle_stop(payload, root, ledger)
    return HookResult({}, "allow", "unsupported_event", project)


def rotate_log_unlocked(path: Path, maximum: int) -> None:
    if not path.is_file() or path.stat().st_size <= maximum:
        return
    data = path.read_bytes()
    tail = data[-(maximum // 2) :]
    newline = tail.find(b"\n")
    if newline >= 0:
        tail = tail[newline + 1 :]
    context_state.atomic_write(path, tail.decode("utf-8", errors="ignore"))


def record_event(
    ledger: Path,
    payload: dict[str, Any],
    result: HookResult,
    duration_ms: float,
    maximum: int = MAX_LOG_BYTES,
) -> None:
    try:
        manifest = context_state.read_json(ledger / "manifest.json")
        event = {
            "at": context_state.utc_now(),
            "event": str(payload.get("hook_event_name") or "unknown"),
            "outcome": result.outcome,
            "reason": result.reason,
            "duration_ms": round(duration_ms, 3),
            "session": stable_id(payload.get("session_id")),
            "turn": stable_id(payload.get("turn_id")),
            "source": str(payload.get("source") or payload.get("trigger") or "")[:32],
            "tool": str(payload.get("tool_name") or "")[:80],
            "task_id": str(manifest.get("task_id", "")),
            "checkpoint": int(manifest.get("checkpoint", 0)),
            "requirements_revision": int(manifest.get("requirements_revision", 0)),
            "requirements_hash": str(manifest.get("recorded_requirements_hash", "")),
        }
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with auxiliary_lock(ledger):
            path = ledger / "hook-events.jsonl"
            line_bytes = len(line.encode("utf-8"))
            if path.is_file() and path.stat().st_size + line_bytes > maximum:
                rotate_log_unlocked(path, max(256, maximum - line_bytes))
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
    except Exception:
        return


def process(payload: dict[str, Any], log_maximum: int = MAX_LOG_BYTES) -> HookResult:
    started = time.perf_counter()
    try:
        result = dispatch(payload)
    except Exception as exc:
        if str(payload.get("hook_event_name") or "") == "PreToolUse":
            result = HookResult(
                deny_tool(f"Durable-context could not resolve one trusted project root: {exc}"),
                "deny",
                "project_resolution_failed",
                None,
            )
        else:
            result = HookResult(
                {"systemMessage": f"Durable-context hook warning: {exc}"},
                "warning",
                "unhandled_hook_error",
                None,
            )
    duration_ms = (time.perf_counter() - started) * 1000
    if result.project:
        record_event(result.project[1], payload, result, duration_ms, maximum=log_maximum)
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="durable-context-hook-") as temporary:
        root = Path(temporary).resolve()
        ledger = root / context_state.DEFAULT_DIR
        context_state.automatic(root, ledger, "start", "Hook regression", "", "", "", "", "active", 3000)
        session = "secret-session-value"
        turn = "turn-1"
        startup = process(
            {"hook_event_name": "SessionStart", "cwd": str(root), "source": "startup", "session_id": session}
        )
        hook_output = startup.payload.get("hookSpecificOutput", {})
        if hook_output.get("hookEventName") != "SessionStart" or "Task ID" not in str(hook_output):
            raise RuntimeError("self-test failed: SessionStart did not return official bounded context")

        prompt_text = "Change the acceptance standard; private-marker-must-not-be-logged"
        prompt = process(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(root),
                "session_id": session,
                "turn_id": turn,
                "prompt": prompt_text,
            }
        )
        if prompt.outcome != "guarded":
            raise RuntimeError("self-test failed: requirement-bearing prompt was not guarded")
        denied = process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(root),
                "session_id": session,
                "turn_id": turn,
                "tool_name": "apply_patch",
                "tool_input": {"command": "private-tool-input"},
            }
        )
        if denied.outcome != "deny" or denied.reason != "requirement_revision_pending":
            raise RuntimeError("self-test failed: unrecorded requirement write was not denied")
        external_denied = process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(root),
                "session_id": session,
                "turn_id": turn,
                "tool_name": "mcp__nuphus__browser_click",
                "tool_input": {"selector": "private-selector"},
            }
        )
        if external_denied.outcome != "deny":
            raise RuntimeError("self-test failed: guarded external-state write was not denied")

        context_state.automatic(
            root,
            ledger,
            "change",
            "",
            "Hook detail recorded",
            "",
            "",
            "",
            "active",
            3000,
            "detail",
            "self-test",
            "guard revision advanced",
            "",
        )
        allowed = process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(root),
                "session_id": session,
                "turn_id": turn,
                "tool_name": "apply_patch",
                "tool_input": {"command": "private-tool-input"},
            }
        )
        if allowed.outcome != "allow":
            raise RuntimeError("self-test failed: recorded requirement write stayed blocked")
        read_only = process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(root),
                "session_id": session,
                "turn_id": "turn-2",
                "tool_name": "Bash",
                "tool_input": {"command": "Get-Content .agent-context\\requirements.md"},
            }
        )
        if read_only.reason != "read_only_tool":
            raise RuntimeError("self-test failed: read-only shell command was misclassified")

        for trigger in ("manual", "auto"):
            compact_turn = f"compact-{trigger}"
            pre = process(
                {
                    "hook_event_name": "PreCompact",
                    "cwd": str(root),
                    "session_id": session,
                    "turn_id": compact_turn,
                    "trigger": trigger,
                }
            )
            post = process(
                {
                    "hook_event_name": "PostCompact",
                    "cwd": str(root),
                    "session_id": session,
                    "turn_id": compact_turn,
                    "trigger": trigger,
                }
            )
            resumed = process(
                {"hook_event_name": "SessionStart", "cwd": str(root), "source": "compact", "session_id": session}
            )
            if pre.reason != "pre_compact_snapshot_saved" or post.reason != "compact_state_match":
                raise RuntimeError(f"self-test failed: {trigger} compaction metadata did not match")
            if resumed.reason != "compact_state_match":
                raise RuntimeError(f"self-test failed: {trigger} compact resume did not verify")

        requirements_path = ledger / "requirements.md"
        requirements_path.write_text(
            requirements_path.read_text(encoding="utf-8") + "\nunauthorized change\n",
            encoding="utf-8",
        )
        corrupt = process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(root),
                "session_id": session,
                "turn_id": "turn-corrupt",
                "tool_name": "apply_patch",
                "tool_input": {"command": "private-corrupt-input"},
            }
        )
        if corrupt.outcome != "deny" or corrupt.reason != "invalid_ledger":
            raise RuntimeError("self-test failed: invalid ledger did not block a write")
        no_ledger = process({"hook_event_name": "PreToolUse", "cwd": str(root.parent)})
        if no_ledger.payload:
            raise RuntimeError("self-test failed: no-ledger project was not ignored")

        log_path = ledger / "hook-events.jsonl"
        log_text = log_path.read_text(encoding="utf-8")
        for secret in (prompt_text, "private-tool-input", "private-corrupt-input", "private-selector", session):
            if secret in log_text:
                raise RuntimeError("self-test failed: sensitive hook input was logged")
        for number in range(30):
            record_event(
                ledger,
                {"hook_event_name": "Stop", "session_id": f"session-{number}"},
                HookResult({}, "allow", "rotation-check", (root, ledger)),
                1.0,
                maximum=1024,
            )
        if log_path.stat().st_size > 1024:
            raise RuntimeError("self-test failed: hook log rotation is not bounded")
    print("codex_hook self-test passed")


def main() -> int:
    configure_utf8_stdio()
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test()
        return 0
    result = process(input_payload())
    return emit(result.payload)


if __name__ == "__main__":
    raise SystemExit(main())
