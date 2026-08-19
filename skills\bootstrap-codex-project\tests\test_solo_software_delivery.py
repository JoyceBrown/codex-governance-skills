from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SoloSoftwareDeliveryContractTests(unittest.TestCase):
    def test_skill_routes_only_matching_delivery_requests(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("references/solo-software-delivery.md", text)
        self.assertIn("first vertical slice", text)
        self.assertIn("continue, simplify, pivot, or stop", text)
        self.assertIn("Do not enable it for an ordinary isolated bug fix", text)

    def test_reference_covers_the_full_evidence_gated_lifecycle(self) -> None:
        text = (
            ROOT / "references" / "solo-software-delivery.md"
        ).read_text(encoding="utf-8")

        for gate in (
            "### 0. Constraints and risk",
            "### 1. Problem evidence",
            "### 2. First-release value loop",
            "### 3. Technical reconnaissance",
            "### 4. Simplest architecture and first vertical slice",
            "### 5. Bounded delivery loop",
            "### 6. Release readiness",
            "### 7. Feedback decision",
        ):
            self.assertIn(gate, text)

        for state in (
            "`ready`",
            "`conditionally ready`",
            "`not ready`",
            "`continue`",
            "`fix`",
            "`simplify`",
            "`pivot`",
            "`stop`",
        ):
            self.assertIn(state, text)

    def test_templates_route_delivery_evidence_to_canonical_owners(self) -> None:
        product = (
            ROOT / "assets" / "templates" / "product.md"
        ).read_text(encoding="utf-8")
        architecture = (
            ROOT / "assets" / "templates" / "architecture.md"
        ).read_text(encoding="utf-8")
        testing = (
            ROOT / "assets" / "templates" / "testing.md"
        ).read_text(encoding="utf-8")
        operations = (
            ROOT / "assets" / "templates" / "operations.md"
        ).read_text(encoding="utf-8")
        decision = (
            ROOT / "assets" / "templates" / "decision.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Problem evidence and current alternative", product)
        self.assertIn("Core value loop", product)
        self.assertIn("Reassessment or stop conditions", product)
        self.assertIn("First vertical slice", architecture)
        self.assertIn("Reuse and custom-build decisions", architecture)
        self.assertIn("Failure-path coverage", testing)
        self.assertIn("Manual acceptance", testing)
        self.assertIn("Rollback and release conditions", operations)
        self.assertIn("Post-release checks", operations)
        self.assertIn("Evidence", decision)
        self.assertIn("Reassessment condition", decision)

    def test_lifecycle_does_not_grant_side_effect_authority(self) -> None:
        text = (
            ROOT / "references" / "solo-software-delivery.md"
        ).read_text(encoding="utf-8")

        self.assertIn("does not itself authorize commits", text)
        self.assertIn(
            "Never perform the release solely because the review passes",
            text,
        )
        self.assertIn("Do not initialize Git, commit, push, publish, deploy", text)
        self.assertNotRegex(text, r"[A-Za-z]:\\")


if __name__ == "__main__":
    unittest.main()
