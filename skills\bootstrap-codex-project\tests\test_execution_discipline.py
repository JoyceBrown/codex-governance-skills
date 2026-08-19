from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExecutionDisciplineContractTests(unittest.TestCase):
    def test_reference_contains_exactly_ten_promoted_rules(self) -> None:
        text = (ROOT / "references" / "execution-discipline.md").read_text(
            encoding="utf-8",
        )

        for index in range(1, 11):
            rule_id = f"ED-{index:02d}"
            self.assertIn(f"### {rule_id}:", text)
        self.assertNotIn("### ED-11:", text)

    def test_skill_routes_only_matching_execution_signals(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("references/execution-discipline.md", text)
        self.assertIn("observable signals match", text)
        self.assertIn("never broaden scope or side-effect permission", text)

    def test_plan_checkpoint_and_handoff_templates_carry_closure_state(self) -> None:
        plan = (ROOT / "assets" / "templates" / "PLANS.md").read_text(
            encoding="utf-8",
        )
        checkpoint = (
            ROOT / "assets" / "templates" / "current-work.md"
        ).read_text(encoding="utf-8")
        handoff = (
            ROOT / "assets" / "templates" / "new-task-handoff.md"
        ).read_text(encoding="utf-8")

        for field in (
            "continuation_policy: validate_then_advance",
            "completion_policy: all_required_items",
            "priority_basis:",
            "delivery_contract:",
        ):
            self.assertIn(field, plan)
        self.assertIn("Attempts and strategy changes", checkpoint)
        self.assertIn("Delivery state", checkpoint)
        self.assertIn("target_resolution:", handoff)
        self.assertIn("verified_capabilities:", handoff)

    def test_rules_preserve_authority_and_side_effect_boundaries(self) -> None:
        text = (ROOT / "references" / "execution-discipline.md").read_text(
            encoding="utf-8",
        )

        self.assertIn("cannot select unauthorized roadmap work", text)
        self.assertIn("does not broaden side-effect permission", text)
        self.assertIn("a delivery contract is not push", text)
        self.assertNotIn("Aegos", text)
        self.assertNotIn("FlClash", text)
        self.assertNotRegex(text, r"[A-Za-z]:\\")


if __name__ == "__main__":
    unittest.main()
