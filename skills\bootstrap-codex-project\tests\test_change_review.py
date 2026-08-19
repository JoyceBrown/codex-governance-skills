from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_TEXT = (ROOT / "SKILL.md").read_text(encoding="utf-8")
REFERENCE_TEXT = (ROOT / "references" / "change-review.md").read_text(
    encoding="utf-8"
)


class ChangeReviewContractTests(unittest.TestCase):
    def test_skill_routes_only_material_change_review_signals(self) -> None:
        self.assertIn("references/change-review.md", SKILL_TEXT)
        self.assertIn("real baseline or prior review record", SKILL_TEXT)
        self.assertIn("Do not enable it for greenfield work", SKILL_TEXT)
        self.assertIn("never invokes a multi-role deliberation workflow", SKILL_TEXT)

    def test_case_axes_and_snapshot_drift_are_explicit(self) -> None:
        for phrase in (
            "continuity_mode: Initial | Re-review",
            "comparison_mode: Current-state | Delta",
            "Manifest-bound",
            "Snapshot-stale",
            "rerun only dependent inspection and judgment work",
        ):
            self.assertIn(phrase, REFERENCE_TEXT)
        self.assertIn("Without a real baseline", REFERENCE_TEXT)

    def test_claim_kind_does_not_replace_project_state(self) -> None:
        for phrase in (
            "claim_kind",
            "`observation`",
            "`judgment`",
            "`preference`",
            "`proposal`",
            "Verified",
            "Decided",
            "Planned",
            "Assumed",
            "Open",
            "axes are orthogonal",
        ):
            self.assertIn(phrase, REFERENCE_TEXT)
        self.assertIn("Do not import a second full finding", REFERENCE_TEXT)

    def test_consequential_evidence_checks_do_not_burden_local_facts(self) -> None:
        self.assertIn("one concrete counterargument", REFERENCE_TEXT)
        self.assertIn("count as one lineage", REFERENCE_TEXT)
        self.assertIn(
            "Do not demand multiple sources for a directly observed local fact",
            REFERENCE_TEXT,
        )

    def test_review_completion_cannot_complete_project_work(self) -> None:
        self.assertIn(
            "review_completion: Complete | Partial | Blocked", REFERENCE_TEXT
        )
        self.assertIn(
            "never sets or implies task, active-plan, release, user-request, or project completion",
            REFERENCE_TEXT,
        )
        self.assertIn(
            "never ends authorized implementation before acceptance criteria",
            REFERENCE_TEXT,
        )


if __name__ == "__main__":
    unittest.main()
