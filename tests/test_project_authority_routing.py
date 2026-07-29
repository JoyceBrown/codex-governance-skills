from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "deliberate-project"
SKILL_TEXT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
REFERENCE_TEXT = (
    SKILL_ROOT / "references" / "project-authority-routing.md"
).read_text(encoding="utf-8")


class ProjectAuthorityRoutingContractTests(unittest.TestCase):
    def test_skill_routes_only_matching_authority_signals(self) -> None:
        self.assertIn("references/project-authority-routing.md", SKILL_TEXT)
        self.assertIn("competing roadmap, plan, status", SKILL_TEXT)
        self.assertIn("without appointing an owner", SKILL_TEXT)
        self.assertIn("treating a recommendation as authorization", SKILL_TEXT)

    def test_owner_and_authority_dimensions_remain_distinct(self) -> None:
        for field in (
            "source_authority",
            "durable_owner",
            "decision_owner",
            "execution_authority",
            "verification_owner",
            "authority_gap",
        ):
            self.assertIn(field, REFERENCE_TEXT)
        self.assertIn("Do not infer one from another", REFERENCE_TEXT)

    def test_bootstrap_filenames_are_not_universal_requirements(self) -> None:
        self.assertIn("semantic roles, not mandatory files", REFERENCE_TEXT)
        self.assertIn("Do not require `PLANS.md`", REFERENCE_TEXT)
        self.assertIn("without imposing filenames", REFERENCE_TEXT)

    def test_requirement_and_technical_change_states_are_orthogonal(self) -> None:
        for field in (
            "requirement_change_class",
            "continuity_mode",
            "comparison_mode",
            "technical_change_state",
            "stakeholder_response_state",
        ):
            self.assertIn(field, REFERENCE_TEXT)
        self.assertIn("A `Delta` is not automatically a roadmap change", REFERENCE_TEXT)

    def test_claim_appropriate_verification_does_not_replace_judgment(self) -> None:
        self.assertIn("Match acceptance evidence to the claim", REFERENCE_TEXT)
        self.assertIn(
            "Mechanical checks cannot establish stakeholder preference",
            REFERENCE_TEXT,
        )

    def test_routing_preserves_read_only_inquiry(self) -> None:
        self.assertIn("advisory and read-only", REFERENCE_TEXT)
        self.assertIn("does not create or update a document", REFERENCE_TEXT)
        self.assertIn("treating a recommendation as authorization", SKILL_TEXT)


if __name__ == "__main__":
    unittest.main()
