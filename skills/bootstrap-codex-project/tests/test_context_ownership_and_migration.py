import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
REFERENCE = (ROOT / "references" / "context-ownership-and-migration.md").read_text(encoding="utf-8")


class ContextOwnershipAndMigrationTests(unittest.TestCase):
    def test_reference_is_routed_for_cold_start_and_competing_context(self) -> None:
        self.assertIn("references/context-ownership-and-migration.md", SKILL)
        self.assertIn("cold-start continuation", SKILL)

    def test_every_context_artifact_has_one_owner(self) -> None:
        for name in ("PLANS.md", "requirements.md", "decisions.md", "findings.md", "handoff.md"):
            self.assertIn(f"`{name}`", REFERENCE)
        self.assertIn("Do not copy the same requirement", REFERENCE)

    def test_migration_classification_and_unknown_boundary_are_explicit(self) -> None:
        for state in ("KEEP", "UPDATE", "ARCHIVE", "SUPERSEDE", "CONFLICT", "UNKNOWN"):
            self.assertIn(f"`{state}`", REFERENCE)
        self.assertIn("missing historical item is an explicit unknown", SKILL)
        self.assertIn("cold-start recovery test", REFERENCE)


if __name__ == "__main__":
    unittest.main()
