import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import context_mcp  # noqa: E402
import context_state  # noqa: E402
import codex_hook  # noqa: E402


class ContinuityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="durable-continuity-test-")
        self.root = Path(self.temp.name)
        self.ledger = self.root / context_state.DEFAULT_DIR
        context_state.automatic(self.root, self.ledger, "start", "Continuity test", "", "", "", "", "active", 3000)
        context_state.automatic(
            self.root,
            self.ledger,
            "checkpoint",
            "",
            "checkpointed",
            "continue",
            "test",
            "",
            "active",
            3000,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_resume_contains_continuity_and_baseline_change_is_visible(self) -> None:
        manifest = context_state.read_json(self.ledger / "manifest.json")
        current = context_state.continuity_snapshot(self.root, self.ledger, manifest)
        self.assertEqual("UNCHANGED", current["baseline_status"])
        (self.root / "PLANS.md").write_text("# Active Execution Plan\n", encoding="utf-8")
        changed = context_state.continuity_snapshot(self.root, self.ledger, manifest)
        self.assertEqual("CHANGED", changed["baseline_status"])
        self.assertIn("plans_hash", changed["changed_fields"])
        resume = context_state.resume(self.ledger, 3000)
        self.assertIn("CONTINUITY STATUS", resume)
        self.assertIn("baseline_status", resume)

    def test_research_receipt_is_an_index_and_not_full_content(self) -> None:
        findings = """# Findings

## Verified

## Research Receipts

### Research Receipt: R-001
- research_id: R-001
- question: Which source is current?
- scope: official docs, 2026-08
- status: VALID
- sources: official docs
- conclusion: Use the current source.
- decision_ref: D-001
- checked_at: 2026-08-18
- superseded_by: none
"""
        (self.ledger / "findings.md").write_text(findings, encoding="utf-8")
        manifest = context_state.read_json(self.ledger / "manifest.json")
        snapshot = context_state.continuity_snapshot(self.root, self.ledger, manifest)
        self.assertEqual(["R-001"], snapshot["research_receipt_refs"])
        self.assertEqual("VALID", snapshot["research_receipts"][0]["status"])
        self.assertEqual("Use the current source.", snapshot["research_receipts"][0]["conclusion"])

    def test_mcp_returns_bounded_missing_states(self) -> None:
        server = context_mcp.ContextServer([self.root])
        missing = server.call_tool("search_context", {"query": "never-present-marker"})
        missing_data = json.loads(missing["content"][0]["text"])
        self.assertEqual("NOT_FOUND", missing_data["status"])
        self.assertFalse(missing_data["blocking"])
        blocked = server.call_tool(
            "search_context",
            {"query": "never-present-marker", "blocking_risk": True},
        )
        blocked_data = json.loads(blocked["content"][0]["text"])
        self.assertEqual("BLOCKED_UNCERTAINTY", blocked_data["status"])
        self.assertTrue(blocked_data["blocking"])
        self.assertIn("searched_scope", blocked_data)
        self.assertIn("budget_used", blocked_data)
        self.assertIn("next_action", blocked_data)

    def test_legacy_migration_rehashes_generated_handoff(self) -> None:
        manifest = context_state.read_json(self.ledger / "manifest.json")
        manifest["version"] = 5
        for key in ("continuity_baseline", "continuity_index", "continuity_status"):
            manifest.pop(key, None)
        context_state.write_manifest(self.ledger, manifest)
        context_state.migrate_ledger(self.ledger, self.root)
        self.assertEqual([], context_state.verify(self.ledger, expected_root=self.root))
        self.assertEqual([], context_state.reconcile(self.ledger, expected_root=self.root)["warnings"])

    def test_project_drift_and_tampered_handoff_close_the_recovery_gate(self) -> None:
        source = self.root / "src.py"
        source.write_text("print('baseline')\n", encoding="utf-8")
        context_state.checkpoint(
            self.ledger,
            "baseline recorded",
            "edit only after verification",
            "test",
            "",
            "active",
            expected_root=self.root,
        )
        source.write_text("print('changed')\n", encoding="utf-8")
        drift = context_state.reconcile(self.ledger, expected_root=self.root)
        self.assertTrue(drift["blocking"])
        self.assertIn("project_fingerprint", drift["baseline_changed"])
        blocked = context_state.resume(self.ledger, 3000)
        self.assertIn("RECOVERY GATE", blocked)
        self.assertNotIn("baseline recorded", blocked)

        context_state.checkpoint(
            self.ledger,
            "rebaselined source",
            "continue",
            "test",
            "",
            "active",
            expected_root=self.root,
        )
        handoff = self.ledger / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8") + "\nforged detail\n", encoding="utf-8")
        tampered = context_state.reconcile(self.ledger, expected_root=self.root)
        self.assertTrue(tampered["blocking"])
        self.assertIn("handoff", " ".join(tampered["blocking_warnings"]))

    def test_research_receipt_requires_integrity_and_freshness_metadata(self) -> None:
        findings = """# Findings

## Verified

## Research Receipts

### Research Receipt: R-001
- research_id: R-001
- question: Which source is current?
- scope: official docs, 2026-08
- status: VALID
- sources: official docs
- conclusion: Use the current source.
- checked_at: 2026-08-18
"""
        (self.ledger / "findings.md").write_text(findings, encoding="utf-8")
        receipt = context_state.research_receipts(self.ledger)[0]
        self.assertEqual("INCOMPLETE", receipt["validation_status"])
        self.assertFalse(receipt["reusable"])

    def test_hook_and_mcp_subprocess_protocols_are_utf8(self) -> None:
        task = "中文连续性任务"
        context_state.automatic(self.root, self.ledger, "switch", task, "pause", "continue", "test", "", "active", 3000)
        hook = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "codex_hook.py")],
            input=(json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.root)}, ensure_ascii=False) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        hook_output = hook.stdout.decode("utf-8")
        self.assertIn(task, hook_output)

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_current_context", "arguments": {}},
        }
        mcp = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "context_mcp.py"), "--allow-root", str(self.root)],
            input=(json.dumps(mcp_request, ensure_ascii=False) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertIn(task, mcp.stdout.decode("utf-8"))

    def test_lifecycle_whitelist_rejects_composite_and_fake_paths(self) -> None:
        command = f'{sys.executable} "{Path(context_state.__file__).resolve()}" --root "{self.root}" auto --event verify'
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        self.assertTrue(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))
        payload["tool_input"]["command"] = command.replace("--event verify", "--event repair")
        self.assertTrue(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))
        payload["tool_input"]["command"] = command + " && whoami"
        self.assertFalse(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))
        payload["tool_input"]["command"] = command.replace("context_state.py", "attacker_context_state.py")
        self.assertFalse(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))

    def test_exec_command_uses_cmd_and_explicit_workdir_for_nested_ledgers(self) -> None:
        child = self.root / "product"
        child.mkdir()
        child_ledger = child / context_state.DEFAULT_DIR
        context_state.automatic(child, child_ledger, "start", "Child task", "", "", "", "", "active", 3000)
        command = f'{sys.executable} "{Path(context_state.__file__).resolve()}" --root "{child}" auto --event verify'
        payload = {
            "hook_event_name": "PreToolUse",
            "cwd": str(self.root),
            "tool_name": "exec_command",
            "tool_input": {"cmd": command, "workdir": str(child)},
        }
        resolved = codex_hook.resolve_project(payload)
        self.assertIsNotNone(resolved)
        self.assertEqual(child.resolve(), resolved[0])
        self.assertTrue(codex_hook.is_lifecycle_repair(payload, child, child_ledger))
        result = codex_hook.process(payload)
        self.assertEqual("allow", result.outcome)
        self.assertEqual("lifecycle_repair", result.reason)

        payload["tool_input"]["cmd"] = command + " && whoami"
        self.assertFalse(codex_hook.is_lifecycle_repair(payload, child, child_ledger))

    def test_nested_ledger_target_routing_fails_closed_on_cross_root_patch(self) -> None:
        child = self.root / "product"
        child.mkdir()
        child_ledger = child / context_state.DEFAULT_DIR
        context_state.automatic(child, child_ledger, "start", "Child task", "", "", "", "", "active", 3000)
        parent_file = self.root / "parent.txt"
        child_file = child / "child.txt"
        parent_file.write_text("parent\n", encoding="utf-8")
        child_file.write_text("child\n", encoding="utf-8")

        child_payload = {
            "hook_event_name": "PreToolUse",
            "cwd": str(self.root),
            "tool_name": "apply_patch",
            "tool_input": {"patch": f"*** Begin Patch\n*** Update File: {child_file}\n*** End Patch"},
        }
        resolved = codex_hook.resolve_project(child_payload)
        self.assertIsNotNone(resolved)
        self.assertEqual(child.resolve(), resolved[0])

        mixed_payload = {
            **child_payload,
            "tool_input": {
                "patch": (
                    f"*** Begin Patch\n*** Update File: {parent_file}\n"
                    f"*** Update File: {child_file}\n*** End Patch"
                )
            },
        }
        result = codex_hook.process(mixed_payload)
        self.assertEqual("deny", result.outcome)
        self.assertEqual("project_resolution_failed", result.reason)

    def test_find_project_rejects_a_manifest_owned_by_another_root(self) -> None:
        rogue = self.root / "rogue"
        rogue_ledger = rogue / context_state.DEFAULT_DIR
        rogue_ledger.mkdir(parents=True)
        manifest = context_state.read_json(self.ledger / "manifest.json")
        context_state.atomic_write(rogue_ledger / "manifest.json", json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "root does not match"):
            codex_hook.find_project(str(rogue))

    def test_repair_rebuilds_only_a_provable_trailing_history_projection(self) -> None:
        context_state.checkpoint(
            self.ledger,
            "recorded checkpoint",
            "continue after verification",
            "test evidence",
            "",
            "active",
            expected_root=self.root,
        )
        history = self.ledger / "history.jsonl"
        lines = history.read_text(encoding="utf-8").splitlines()
        history.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        handoff = self.ledger / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8") + "\ninterrupted projection\n", encoding="utf-8")

        result = context_state.automatic(
            self.root,
            self.ledger,
            "repair",
            "",
            "",
            "",
            "",
            "",
            "active",
            3000,
        )
        self.assertEqual("repaired", result["action"])
        self.assertIn("history.jsonl checkpoint 2", result["repaired"])
        self.assertIn("handoff.md", result["repaired"])
        self.assertEqual([], context_state.verify(self.ledger, expected_root=self.root))
        self.assertTrue(any(entry.get("kind") == "repair" for entry in context_state.read_changes(self.ledger, 100)))

    def test_projection_repair_preserves_project_drift_for_explicit_rebaseline(self) -> None:
        source = self.root / "source.py"
        source.write_text("baseline\n", encoding="utf-8")
        context_state.checkpoint(
            self.ledger,
            "recorded checkpoint",
            "continue after verification",
            "test evidence",
            "",
            "active",
            expected_root=self.root,
        )
        history = self.ledger / "history.jsonl"
        lines = history.read_text(encoding="utf-8").splitlines()
        history.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        source.write_text("drifted\n", encoding="utf-8")

        result = context_state.repair_ledger(self.root, self.ledger)

        self.assertEqual("repaired", result["action"])
        self.assertTrue(result["rebaseline_required"])
        self.assertEqual([], context_state.verify(self.ledger, expected_root=self.root))
        self.assertTrue(context_state.reconcile(self.ledger, expected_root=self.root)["blocking"])

    def test_repair_refuses_ambiguous_history_and_preserves_the_projection(self) -> None:
        context_state.checkpoint(
            self.ledger,
            "recorded checkpoint",
            "continue after verification",
            "test evidence",
            "",
            "active",
            expected_root=self.root,
        )
        history = self.ledger / "history.jsonl"
        lines = history.read_text(encoding="utf-8").splitlines()
        history.write_text("\n".join(lines + [lines[-1]]) + "\n", encoding="utf-8")
        before = history.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "RECOVERY_REQUIRED"):
            context_state.repair_ledger(self.root, self.ledger)
        self.assertEqual(before, history.read_text(encoding="utf-8"))

    def test_repair_does_not_replace_a_current_handoff_after_requirement_change(self) -> None:
        current_requirements = (self.ledger / "requirements.md").read_text(encoding="utf-8")
        revised = current_requirements.replace(
            "## Current Revision\n0",
            "## Current Revision\n1",
        )
        context_state.change(
            self.ledger,
            "Updated current requirement detail",
            "clarification",
            "test",
            "The current handoff is authoritative until a later checkpoint.",
            revised,
            expected_root=self.root,
        )
        handoff = self.ledger / "handoff.md"
        before = handoff.read_text(encoding="utf-8")
        result = context_state.repair_ledger(self.root, self.ledger)
        self.assertEqual("already_valid", result["action"])
        self.assertEqual(before, handoff.read_text(encoding="utf-8"))

    def test_session_start_attempts_one_trusted_repair_before_blocking(self) -> None:
        context_state.checkpoint(
            self.ledger,
            "recorded checkpoint",
            "continue after verification",
            "test evidence",
            "",
            "active",
            expected_root=self.root,
        )
        history = self.ledger / "history.jsonl"
        lines = history.read_text(encoding="utf-8").splitlines()
        history.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        result = codex_hook.process({"hook_event_name": "SessionStart", "cwd": str(self.root)})
        self.assertEqual("allow", result.outcome)
        self.assertEqual("resume_verified", result.reason)
        self.assertEqual([], context_state.verify(self.ledger, expected_root=self.root))

    def test_stop_opens_a_circuit_after_repeated_identical_recovery_failure(self) -> None:
        (self.ledger / ".transaction.json").write_text("{}\n", encoding="utf-8")
        payload = {"hook_event_name": "Stop", "cwd": str(self.root), "session_id": "same-session"}
        first = codex_hook.process(payload)
        second = codex_hook.process(payload)
        third = codex_hook.process(payload)
        self.assertEqual("continue", first.outcome)
        self.assertEqual("dirty_ledger", first.reason)
        self.assertEqual("warning", second.outcome)
        self.assertEqual("recovery_circuit_open", second.reason)
        self.assertNotIn("decision", second.payload)
        self.assertEqual("recovery_circuit_open", third.reason)

        (self.ledger / ".transaction.json").unlink()
        context_state.checkpoint(
            self.ledger,
            "transaction recovery verified",
            "continue",
            "test evidence",
            "",
            "active",
            expected_root=self.root,
        )
        clean = codex_hook.process(payload)
        self.assertEqual("active_clean", clean.reason)

    def test_requirement_hint_is_observed_without_a_write_gate(self) -> None:
        session = "hint-session"
        turn = "hint-turn"
        prompt = codex_hook.process(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.root),
                "session_id": session,
                "turn_id": turn,
                "prompt": "Change the acceptance standard after reviewing the current evidence.",
            }
        )
        self.assertEqual("allow", prompt.outcome)
        self.assertEqual("requirement_observed", prompt.reason)
        self.assertEqual({}, prompt.payload)

        write = codex_hook.process(
            {
                "hook_event_name": "PreToolUse",
                "cwd": str(self.root),
                "session_id": session,
                "turn_id": turn,
                "tool_name": "apply_patch",
                "tool_input": {"patch": "*** Begin Patch\n*** End Patch"},
            }
        )
        self.assertEqual("allow", write.outcome)
        self.assertEqual("ledger_valid", write.reason)

        stop = codex_hook.process(
            {"hook_event_name": "Stop", "cwd": str(self.root), "session_id": session, "turn_id": turn}
        )
        self.assertEqual("active_clean", stop.reason)
        self.assertNotIn("decision", stop.payload)

    def test_stop_downgrades_ledger_bookkeeping_to_one_advisory(self) -> None:
        consistency = {
            "errors": ["complete ledger has unfinished Acceptance Standard items"],
            "warnings": ["requirements revision mismatch: change log=2, manifest=0"],
            "blocking_warnings": [],
        }
        payload = {"hook_event_name": "Stop", "cwd": str(self.root), "session_id": "advisory-session"}
        with mock.patch.object(codex_hook.context_state, "reconcile", return_value=consistency):
            result = codex_hook.process(payload)
        self.assertEqual("warning", result.outcome)
        self.assertEqual("ledger_advisory", result.reason)
        self.assertEqual({}, result.payload)

    def test_invalid_ledger_prompt_hint_is_telemetry_only(self) -> None:
        requirements = self.ledger / "requirements.md"
        requirements.write_text(requirements.read_text(encoding="utf-8") + "\ninvalid change\n", encoding="utf-8")
        result = codex_hook.process(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.root),
                "session_id": "invalid-prompt-session",
                "turn_id": "invalid-prompt-turn",
                "prompt": "继续",
            }
        )
        self.assertEqual("warning", result.outcome)
        self.assertEqual("invalid_ledger_observed", result.reason)
        self.assertEqual({}, result.payload)


if __name__ == "__main__":
    unittest.main()
