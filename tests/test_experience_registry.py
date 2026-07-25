from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from experience_registry import (  # noqa: E402
    assess_promotion,
    capture,
    configure,
    default_store,
    find_record,
    load_config,
    mark_promoted,
    relevant,
    review,
)


class ExperienceRegistryTests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        return temporary, Path(temporary.name) / "registry"

    def capture_example(
        self,
        store: Path,
        *,
        project_root: str,
        scope: str = "cross_project",
        severity: str = "medium",
        reproduced: bool = False,
        evidence: list[str] | None = None,
    ):
        return capture(
            store,
            problem="Generated every possible documentation file",
            observed_failure="The user could not find the active project facts",
            preferred_response="Generate only artifacts justified by repository evidence",
            scope=scope,
            project_root=project_root,
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
            evidence=evidence or ["A real audit found duplicate authority"],
            severity=severity,
            reproduced=reproduced,
        )

    def test_default_store_respects_codex_home(self) -> None:
        with patch.dict(os.environ, {"CODEX_HOME": "D:/codex-home"}):
            self.assertEqual(
                Path("D:/codex-home/learning/bootstrap-codex-project"),
                default_store(),
            )

    def test_capture_sanitizes_secrets_and_personal_paths(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)

        fake_key = "as_" + "sk_" + "1234567890abcdefghijkl"
        record, created = capture(
            store,
            problem=f"Token {fake_key} leaked",
            observed_failure=r"Read C:\Users\Alice\private\log.txt",
            preferred_response="Store only sanitized summaries",
            scope="cross_project",
            project_root=temporary.name,
            signals=["secret-risk"],
        )

        self.assertTrue(created)
        self.assertNotIn("as_sk_", record["problem"])
        self.assertNotIn("Alice", record["observed_failure"])
        self.assertIn("[REDACTED_SECRET]", record["problem"])
        self.assertIn("<user-home>", record["observed_failure"])

    def test_duplicate_capture_merges_occurrences_and_projects(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        first, created = self.capture_example(store, project_root="D:/project-one")
        second, created_again = self.capture_example(store, project_root="D:/project-two")

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["pattern_id"], second["pattern_id"])
        self.assertEqual(2, second["occurrence_count"])
        self.assertEqual(2, len(second["project_fingerprints"]))

    def test_candidate_is_not_recommended_until_accepted(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")

        self.assertEqual([], relevant(store, project_types=["desktop-app"]))
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="The behavior is useful across matching projects",
        )

        matches = relevant(
            store,
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
        )
        self.assertEqual([record["pattern_id"]], [item["pattern_id"] for item in matches])

    def test_project_family_requires_matching_type(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(
            store,
            project_root="D:/project-one",
            scope="project_family",
        )
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Only applies to desktop apps",
        )

        self.assertEqual(
            [],
            relevant(
                store,
                project_types=["web-api"],
                signals=["duplicate-docs"],
            ),
        )
        self.assertEqual(
            1,
            len(
                relevant(
                    store,
                    project_types=["desktop-app"],
                    signals=["duplicate-docs"],
                )
            ),
        )

    def test_recorded_signal_must_match_before_recommendation(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Useful when duplicate documentation is present",
        )

        self.assertEqual([], relevant(store, project_types=["desktop-app"]))
        self.assertEqual(
            [],
            relevant(
                store,
                project_types=["desktop-app"],
                signals=["unrelated-risk"],
            ),
        )

    def test_promotion_requires_generalization_evidence(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Locally useful",
        )

        assessment = assess_promotion(find_record(store, record["pattern_id"]))
        self.assertFalse(assessment["eligible_for_promotion_review"])

        self.capture_example(store, project_root="D:/project-two")
        assessment = assess_promotion(find_record(store, record["pattern_id"]))
        self.assertTrue(assessment["eligible_for_promotion_review"])

    def test_reproduced_severe_failure_can_enter_promotion_review(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(
            store,
            project_root="D:/project-one",
            severity="high",
            reproduced=True,
            evidence=["Reproduction case", "Counterexample case"],
        )
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Severe and reproducible",
        )

        assessment = assess_promotion(find_record(store, record["pattern_id"]))
        self.assertTrue(assessment["eligible_for_promotion_review"])

    def test_promoted_pattern_is_not_reinjected(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        self.capture_example(store, project_root="D:/project-two")
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Validated in two independent projects",
        )
        mark_promoted(
            store,
            pattern_id=record["pattern_id"],
            target=["references/experience-learning.md"],
            regression_tests=["tests/test_experience_registry.py"],
            approval_note="User approved the Skill update",
        )

        self.assertEqual([], relevant(store, project_types=["desktop-app"]))

    def test_capture_mode_defaults_to_ask_and_can_be_configured(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)

        self.assertEqual({"capture_mode": "ask"}, load_config(store))
        configure(store, "auto_sanitized")
        self.assertEqual({"capture_mode": "auto_sanitized"}, load_config(store))


if __name__ == "__main__":
    unittest.main()
