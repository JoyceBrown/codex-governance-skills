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
    audit_registry,
    assess_promotion,
    capture,
    configure,
    default_store,
    find_record,
    load_config,
    load_records,
    mark_promoted,
    observe_outcome,
    relevant,
    review,
    finalize_run,
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
        configure(store, "auto_sanitized")
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
        configure(store, "auto_sanitized")
        record, created = capture(
            store,
            problem=f"Token {fake_key} and alice@example.com leaked",
            observed_failure=(
                r"Read C:\Users\Alice\private\log.txt from "
                "postgresql://admin:secret@db.example/app with password=hunter2"
            ),
            preferred_response="Store only sanitized summaries",
            scope="cross_project",
            project_root=temporary.name,
            signals=["secret-risk"],
        )

        self.assertTrue(created)
        self.assertNotIn("as_sk_", record["problem"])
        self.assertNotIn("Alice", record["observed_failure"])
        self.assertIn("[REDACTED_SECRET]", record["problem"])
        self.assertNotIn("alice@example.com", record["problem"])
        self.assertNotIn("admin:secret", record["observed_failure"])
        self.assertNotIn("hunter2", record["observed_failure"])
        self.assertIn("[REDACTED_EMAIL]", record["problem"])
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

    def test_project_specific_capture_never_merges_across_projects(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        first, _ = self.capture_example(
            store,
            project_root="D:/project-one",
            scope="project_specific",
        )
        second, _ = self.capture_example(
            store,
            project_root="D:/project-two",
            scope="project_specific",
        )

        self.assertNotEqual(first["pattern_id"], second["pattern_id"])
        self.assertEqual(2, len(load_records(store)))

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
            forward_tests=["representative project passed"],
            regression_tests=["unit suite passed"],
            approval_note="User approved the Skill update",
            user_approved=True,
        )

        self.assertEqual([], relevant(store, project_types=["desktop-app"]))

    def test_capture_mode_defaults_to_auto_sanitized_and_can_be_configured(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)

        self.assertEqual({"capture_mode": "auto_sanitized"}, load_config(store))
        configure(store, "auto_sanitized")
        self.assertEqual({"capture_mode": "auto_sanitized"}, load_config(store))

    def test_capture_modes_are_enforced(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        arguments = {
            "problem": "Repeated failure",
            "observed_failure": "Validation missed it",
            "preferred_response": "Detect it deterministically",
            "scope": "cross_project",
            "signals": ["validator-gap"],
        }

        configure(store, "off")
        with self.assertRaisesRegex(ValueError, "disabled"):
            capture(store, **arguments)

        configure(store, "ask")
        with self.assertRaisesRegex(ValueError, "confirmation"):
            capture(store, **arguments)
        record, created = capture(store, **arguments, confirmed=True)
        self.assertTrue(created)
        self.assertEqual("candidate", record["status"])

    def test_invalid_review_transitions_are_rejected(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Accepted for matching local projects",
        )
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="retire",
            reason="Superseded by current platform behavior",
        )

        with self.assertRaisesRegex(ValueError, "invalid experience transition"):
            review(
                store,
                pattern_id=record["pattern_id"],
                decision="accept",
                reason="Attempt to reactivate",
            )

    def test_conflicting_new_experience_requires_explicit_supersession(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        previous, _ = self.capture_example(store, project_root="D:/project-one")
        review(
            store,
            pattern_id=previous["pattern_id"],
            decision="accept",
            reason="Current locally reviewed behavior",
        )
        replacement, created = capture(
            store,
            problem="Generated every possible documentation file",
            observed_failure="New evidence showed the old response was harmful",
            preferred_response="Preserve the complete existing documentation set",
            scope="cross_project",
            project_root="D:/project-two",
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
            evidence=["A newer audit contradicted the accepted response"],
        )

        self.assertTrue(created)
        self.assertEqual([previous["pattern_id"]], replacement["conflicts_with"])
        with self.assertRaisesRegex(ValueError, "requires supersedes"):
            review(
                store,
                pattern_id=replacement["pattern_id"],
                decision="accept",
                reason="New evidence replaces the old response",
            )

        review(
            store,
            pattern_id=replacement["pattern_id"],
            decision="accept",
            reason="New evidence replaces the old response",
            supersedes=[previous["pattern_id"]],
        )
        retired = find_record(store, previous["pattern_id"])
        self.assertEqual("retired", retired["status"])
        self.assertEqual(replacement["pattern_id"], retired["superseded_by"])

    def test_promotion_requires_approval_and_passed_test_evidence(self) -> None:
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
        common = {
            "pattern_id": record["pattern_id"],
            "target": ["SKILL.md"],
            "forward_tests": ["representative fixture passed"],
            "regression_tests": ["unit suite passed"],
            "approval_note": "User approved this general Skill rule",
        }

        with self.assertRaisesRegex(ValueError, "explicit user approval"):
            mark_promoted(store, **common, user_approved=False)
        with self.assertRaisesRegex(ValueError, "include a passed"):
            mark_promoted(
                store,
                **{**common, "forward_tests": ["representative fixture"]},
                user_approved=True,
            )

    def test_malformed_record_fails_closed(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        candidates = store / "candidates"
        candidates.mkdir(parents=True)
        (candidates / "EXP-20260727-deadbeef.json").write_text(
            "{not-json}\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "cannot read experience record"):
            load_records(store)

    def test_two_independent_captures_automatically_enter_shadow(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        self.assertEqual("candidate", record["status"])

        record, _ = self.capture_example(store, project_root="D:/project-two")
        self.assertEqual("shadow", record["status"])
        matches = relevant(
            store,
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
        )
        self.assertEqual("verify_only", matches[0]["use_mode"])

    def test_two_independent_shadow_benefits_automatically_activate(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        record, _ = self.capture_example(store, project_root="D:/project-two")

        observe_outcome(
            store,
            pattern_id=record["pattern_id"],
            kind="shadow_benefit",
            summary="The check prevented duplicate authority",
            project_root="D:/validation-one",
        )
        result = observe_outcome(
            store,
            pattern_id=record["pattern_id"],
            kind="shadow_benefit",
            summary="The check found the same risk before editing",
            project_root="D:/validation-two",
        )

        self.assertEqual("active", result["record"]["status"])
        matches = relevant(
            store,
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
        )
        self.assertEqual("apply_advisory", matches[0]["use_mode"])

    def test_outcome_and_audit_are_idempotent(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        record, _ = self.capture_example(store, project_root="D:/project-two")
        first = observe_outcome(
            store,
            pattern_id=record["pattern_id"],
            kind="shadow_benefit",
            summary="Validation helped",
            project_root="D:/validation-one",
        )
        second = observe_outcome(
            store,
            pattern_id=record["pattern_id"],
            kind="shadow_benefit",
            summary="Validation helped",
            project_root="D:/validation-one",
        )

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual([], audit_registry(store)["transitions"])

    def test_regression_automatically_rolls_back_active_experience(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        review(
            store,
            pattern_id=record["pattern_id"],
            decision="accept",
            reason="Explicit emergency acceptance for the fixture",
        )
        result = observe_outcome(
            store,
            pattern_id=record["pattern_id"],
            kind="regression",
            summary="The advice hid a valid project owner",
            project_root="D:/regression-project",
        )

        self.assertEqual("rolled_back", result["record"]["status"])
        self.assertEqual(
            [],
            relevant(
                store,
                project_types=["desktop-app"],
                signals=["duplicate-docs"],
            ),
        )

    def test_conflict_with_promoted_rule_is_quarantined_without_overriding_it(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        promoted, _ = self.capture_example(store, project_root="D:/project-one")
        self.capture_example(store, project_root="D:/project-two")
        review(
            store,
            pattern_id=promoted["pattern_id"],
            decision="accept",
            reason="Fixture promotion acceptance",
        )
        mark_promoted(
            store,
            pattern_id=promoted["pattern_id"],
            target=["SKILL.md"],
            forward_tests=["fixture passed"],
            regression_tests=["suite passed"],
            approval_note="User approved the fixture promotion",
            user_approved=True,
        )
        replacement, _ = capture(
            store,
            problem="Generated every possible documentation file",
            observed_failure="A contradictory lesson was captured",
            preferred_response="Always generate every available documentation artifact",
            scope="cross_project",
            project_root="D:/project-three",
            project_types=["desktop-app"],
            signals=["duplicate-docs"],
            evidence=["Contradictory evidence"],
        )

        self.assertEqual("conflicted", replacement["status"])
        self.assertEqual("promoted", find_record(store, promoted["pattern_id"])["status"])

    def test_schema_v1_records_migrate_without_losing_review_metadata(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)
        record, _ = self.capture_example(store, project_root="D:/project-one")
        path = store / "candidates" / f"{record['pattern_id']}.json"
        import json

        legacy = json.loads(path.read_text(encoding="utf-8"))
        legacy["schema_version"] = 1
        legacy["status"] = "accepted_local"
        legacy["review"] = {"decision": "accept", "reason": "Legacy approval", "reviewed_at": legacy["last_seen_at"]}
        legacy.pop("lifecycle")
        legacy.pop("outcomes")
        path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        migrated = find_record(store, record["pattern_id"])
        self.assertEqual(2, migrated["schema_version"])
        self.assertEqual("active", migrated["status"])
        self.assertEqual("Legacy approval", migrated["review"]["reason"])
        audit_registry(store)
        persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(2, persisted["schema_version"])

    def test_finalize_writes_no_eligible_experience_receipt(self) -> None:
        temporary, store = self.make_store()
        self.addCleanup(temporary.cleanup)

        result = finalize_run(store, run_summary="No reusable friction occurred")

        self.assertEqual("no-eligible-experience", result["outcome"])
        self.assertTrue(Path(result["receipt"]).exists())


if __name__ == "__main__":
    unittest.main()
