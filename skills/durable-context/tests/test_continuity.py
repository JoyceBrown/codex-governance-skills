import json
import subprocess
import sys
import tempfile
import unittest
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
        payload["tool_input"]["command"] = command + " && whoami"
        self.assertFalse(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))
        payload["tool_input"]["command"] = command.replace("context_state.py", "attacker_context_state.py")
        self.assertFalse(codex_hook.is_lifecycle_repair(payload, self.root, self.ledger))


if __name__ == "__main__":
    unittest.main()
