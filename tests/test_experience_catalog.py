from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "deliberate-project" / "scripts" / "experience_catalog.py"


class ExperienceCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        base = Path(self.tempdir.name)
        self.root = base / "experience-root"
        self.root.mkdir()
        codex_home = base / "codex-home"
        codex_home.mkdir()
        (codex_home / "deliberate-project-experience-root.txt").write_text(
            str(self.root), encoding="utf-8"
        )
        self.env = os.environ.copy()
        self.env["CODEX_HOME"] = str(codex_home)
        self.env.pop("AEGOS_SKILLS_EXPERIENCE_ROOT", None)
        self.env.pop("DELIBERATE_PROJECT_EXPERIENCE_CONFIG", None)

    @property
    def database(self) -> Path:
        return self.root / "deliberate-project" / "experience.sqlite3"

    def run_cli(self, *args: str, expect_ok: bool = True) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
        )
        if expect_ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        if result.stderr.startswith("{"):
            return json.loads(result.stderr)
        return {"error": result.stderr}

    def observe(
        self,
        *,
        case_id: str,
        claim: str = "Stable project lesson",
        outcome: str = "candidate",
        high_risk: bool = False,
        source: str | list[str] = "source:test-suite",
        related_lesson_id: str | None = None,
        expect_ok: bool = True,
    ) -> dict[str, object]:
        args = [
            "observe",
            "--case-id",
            case_id,
            "--claim",
            claim,
            "--scope",
            "software-projects",
            "--version-scope",
            "all-supported",
            "--jurisdiction",
            "global",
            "--expires-at",
            "2099-12-31",
            "--recheck-trigger",
            "material workflow change",
            "--limitations",
            "verified test fixture only",
            "--outcome",
            outcome,
        ]
        for source_item in ([source] if isinstance(source, str) else source):
            args.extend(["--source", source_item])
        args.extend([
            "--evidence-id",
            f"evidence:{case_id}",
            "--snapshot-id",
            f"snapshot:{case_id}",
            "--verification-method",
            "deterministic test",
            "--verified",
            "--privacy-reviewed",
            "--license-reviewed",
        ])
        if high_risk:
            args.append("--high-risk-fix")
        if related_lesson_id:
            args.extend(["--related-lesson-id", related_lesson_id])
        return self.run_cli(*args, expect_ok=expect_ok)

    def promote_to_shadow(self, claim: str, case_id: str) -> str:
        result = self.observe(
            case_id=case_id, claim=claim, high_risk=True
        )
        self.assertEqual(result["after_status"], "Shadow")
        return str(result["lesson_id"])

    def test_out_of_order_observation_is_rejected(self) -> None:
        self.observe(case_id="candidate-1")
        result = self.observe(
            case_id="benefit-too-early",
            outcome="shadow-benefit",
            expect_ok=False,
        )
        self.assertIn("invalid for Candidate", str(result["error"]))

    def test_duplicate_case_is_idempotent(self) -> None:
        first = self.observe(case_id="duplicate-case")
        second = self.observe(case_id="duplicate-case", high_risk=True)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertFalse(second["changed"])
        self.assertEqual(second["status"], "Candidate")
        self.assertEqual(second["verified_observation_counts"]["candidate"], 1)

    def test_duplicate_event_remains_idempotent_after_state_change(self) -> None:
        first = self.observe(case_id="promoting-case", high_risk=True)
        replay = self.observe(case_id="promoting-case", high_risk=True)
        self.assertEqual(first["status"], "Shadow")
        self.assertEqual(replay["status"], "Shadow")
        self.assertTrue(replay["duplicate"])
        self.assertFalse(replay["changed"])
        self.assertEqual(replay["verified_observation_counts"]["candidate"], 1)

    def test_only_post_shadow_benefits_promote_to_active(self) -> None:
        lesson_id = self.promote_to_shadow("Promotion lesson", "promotion-candidate")
        first = self.observe(
            case_id="benefit-1",
            claim="Promotion lesson",
            outcome="shadow-benefit",
            source="source:independent-benefit-1",
        )
        second = self.observe(
            case_id="benefit-2",
            claim="Promotion lesson",
            outcome="shadow-benefit",
            source="source:independent-benefit-2",
        )
        self.assertEqual(first["status"], "Shadow")
        self.assertEqual(second["status"], "Active")
        self.assertEqual(second["verified_shadow_benefit_cases"], 2)
        self.assertEqual(
            second["verified_independent_shadow_benefit_lineages"], 2
        )
        self.assertEqual(second["lesson_id"], lesson_id)

    def test_same_lineage_cases_do_not_satisfy_promotion_gates(self) -> None:
        first = self.observe(case_id="same-lineage-candidate-1")
        second = self.observe(case_id="same-lineage-candidate-2")
        self.assertEqual(first["status"], "Candidate")
        self.assertEqual(second["status"], "Candidate")
        self.assertEqual(second["verified_observation_counts"]["candidate"], 2)
        self.assertEqual(second["verified_independent_candidate_lineages"], 1)

        third = self.observe(
            case_id="independent-candidate",
            source="source:independent-candidate",
        )
        self.assertEqual(third["status"], "Shadow")
        self.assertEqual(third["verified_independent_candidate_lineages"], 2)

    def test_same_lineage_shadow_benefits_do_not_activate_lesson(self) -> None:
        self.promote_to_shadow("Correlated benefit lesson", "benefit-candidate")
        self.observe(
            case_id="correlated-benefit-1",
            claim="Correlated benefit lesson",
            outcome="shadow-benefit",
        )
        second = self.observe(
            case_id="correlated-benefit-2",
            claim="Correlated benefit lesson",
            outcome="shadow-benefit",
        )
        self.assertEqual(second["status"], "Shadow")
        self.assertEqual(second["verified_shadow_benefit_cases"], 2)
        self.assertEqual(
            second["verified_independent_shadow_benefit_lineages"], 1
        )

    def test_shared_source_transitively_forms_one_lineage_component(self) -> None:
        self.observe(
            case_id="component-a",
            source=["source:origin-a", "source:shared-upstream"],
        )
        second = self.observe(
            case_id="component-b",
            source=["source:shared-upstream", "source:origin-b"],
        )
        self.assertEqual(second["status"], "Candidate")
        self.assertEqual(second["verified_independent_candidate_lineages"], 1)

        third = self.observe(
            case_id="component-c", source="source:independent-origin"
        )
        self.assertEqual(third["status"], "Shadow")
        self.assertEqual(third["verified_independent_candidate_lineages"], 2)

    def test_regression_rolls_back_shadow_but_not_candidate(self) -> None:
        self.observe(case_id="ordinary-candidate", claim="Candidate lesson")
        invalid = self.observe(
            case_id="candidate-regression",
            claim="Candidate lesson",
            outcome="shadow-regression",
            expect_ok=False,
        )
        self.assertIn("invalid for Candidate", str(invalid["error"]))
        self.promote_to_shadow("Rollback lesson", "rollback-candidate")
        rolled_back = self.observe(
            case_id="rollback-regression",
            claim="Rollback lesson",
            outcome="shadow-regression",
        )
        self.assertEqual(rolled_back["status"], "Rolled-back")

    def test_conflict_can_be_resolved_with_audited_evidence(self) -> None:
        first_id = self.promote_to_shadow("First conflicting lesson", "first-candidate")
        second_id = self.promote_to_shadow(
            "Second conflicting lesson", "second-candidate"
        )
        conflict = self.observe(
            case_id="conflict-case",
            claim="First conflicting lesson",
            outcome="conflict",
            related_lesson_id=second_id,
        )
        self.assertEqual(conflict["status"], "Conflicted")
        resolved = self.run_cli(
            "resolve-conflict",
            "--lesson-id",
            first_id,
            "--related-lesson-id",
            second_id,
            "--action",
            "keep-first",
            "--reason",
            "verified contradiction resolution",
            "--source",
            "source:test-suite",
            "--evidence-id",
            "evidence:conflict-resolution",
            "--snapshot-id",
            "snapshot:conflict-resolution",
            "--verification-method",
            "deterministic test",
            "--verified",
            "--privacy-reviewed",
            "--license-reviewed",
        )
        self.assertEqual(resolved["first_lesson"]["status"], "Shadow")
        self.assertEqual(resolved["second_lesson"]["status"], "Deprecated")
        shown = self.run_cli("show", "--lesson-id", first_id)
        self.assertEqual(shown["conflict_resolutions"][0]["action"], "keep-first")

    def test_load_excludes_expired_without_writing_status(self) -> None:
        lesson_id = self.promote_to_shadow("Expired lesson", "expired-candidate")
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "UPDATE lessons SET expires_at = '2000-01-01' WHERE lesson_id = ?",
                (lesson_id,),
            )
            connection.commit()
        finally:
            connection.close()
        loaded = self.run_cli("load")
        self.assertEqual(loaded["lessons"], [])
        connection = sqlite3.connect(self.database)
        try:
            status = connection.execute(
                "SELECT status FROM lessons WHERE lesson_id = ?", (lesson_id,)
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(status, "Shadow")

    def test_cli_root_override_is_not_available(self) -> None:
        outside = Path(self.tempdir.name) / "unapproved-root"
        result = self.run_cli("--root", str(outside), "list", expect_ok=False)
        self.assertIn("invalid choice", str(result["error"]))
        self.assertFalse(outside.exists())

    def test_migrate_refuses_to_create_a_missing_catalog(self) -> None:
        result = self.run_cli("migrate", expect_ok=False)
        self.assertIn("does not exist", str(result["error"]))
        self.assertFalse(self.database.exists())

    def test_v1_migration_preserves_history_without_new_verification_credit(self) -> None:
        self.database.parent.mkdir()
        connection = sqlite3.connect(self.database)
        try:
            connection.executescript(
                """
                CREATE TABLE lessons (
                    lesson_id TEXT PRIMARY KEY, claim TEXT NOT NULL,
                    scope TEXT NOT NULL, version_scope TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL, expires_at TEXT NOT NULL,
                    recheck_trigger TEXT NOT NULL, limitations TEXT NOT NULL,
                    high_risk_fix INTEGER NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
                    case_id TEXT NOT NULL, outcome TEXT NOT NULL,
                    source_lineage_json TEXT NOT NULL, note TEXT NOT NULL,
                    related_lesson_id TEXT, created_at TEXT NOT NULL,
                    UNIQUE (lesson_id, case_id, outcome)
                );
                CREATE TABLE transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT NOT NULL REFERENCES lessons(lesson_id),
                    from_status TEXT NOT NULL, to_status TEXT NOT NULL,
                    reason TEXT NOT NULL, created_at TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                """
            )
            connection.execute(
                "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "0123456789abcdef01234567",
                    "Legacy lesson",
                    "software-projects",
                    "all-supported",
                    "global",
                    "2099-12-31",
                    "material workflow change",
                    "legacy fixture",
                    1,
                    "Shadow",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO observations "
                "(lesson_id, case_id, outcome, source_lineage_json, note, "
                "related_lesson_id, created_at) VALUES (?, ?, ?, ?, '', NULL, ?)",
                (
                    "0123456789abcdef01234567",
                    "legacy-case",
                    "candidate",
                    '["hash:0123456789abcdef"]',
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        migrated = self.run_cli("migrate")
        self.assertEqual(migrated["before_schema_version"], 1)
        self.assertEqual(migrated["after_schema_version"], 2)
        shown = self.run_cli(
            "show", "--lesson-id", "0123456789abcdef01234567"
        )
        self.assertEqual(shown["observations"][0]["verification_state"], "Legacy-attested")
        self.assertEqual(shown["verified_observation_counts"]["candidate"], 0)
        self.assertEqual(shown["all_observation_counts"]["candidate"], 1)


if __name__ == "__main__":
    unittest.main()
