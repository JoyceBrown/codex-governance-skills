import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import context_mcp  # noqa: E402
import context_state  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
