from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "deliberate-project"
SKILL_TEXT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
ROUTING_TEXT = (
    SKILL_ROOT / "references" / "retrieval-routing.md"
).read_text(encoding="utf-8")


class SkillContractTests(unittest.TestCase):
    def test_retrieval_reference_is_routed_from_core_skill(self) -> None:
        self.assertIn("references/retrieval-routing.md", SKILL_TEXT)

    def test_routing_uses_hard_filters_and_runtime_selection(self) -> None:
        for phrase in (
            "Apply these hard filters first",
            "Re-evaluate the route",
            "No search provider",
            "source_origin_and_lineage",
            "Failure and Fallback",
        ):
            self.assertIn(phrase, SKILL_TEXT + ROUTING_TEXT)

    def test_anysearch_is_conditional_not_permanently_preferred(self) -> None:
        self.assertIn("when it is installed, approved, and selected", ROUTING_TEXT)
        self.assertIn("Do not select AnySearch merely because it is installed", ROUTING_TEXT)
        self.assertNotIn("Always use AnySearch", SKILL_TEXT + ROUTING_TEXT)

    def test_high_risk_retrieval_boundaries_are_explicit(self) -> None:
        for phrase in (
            "split it into separate claims",
            "sampling contract",
            "incidental read effects",
            "missing, unreadable, or incompatible",
        ):
            self.assertIn(phrase, ROUTING_TEXT)


if __name__ == "__main__":
    unittest.main()
