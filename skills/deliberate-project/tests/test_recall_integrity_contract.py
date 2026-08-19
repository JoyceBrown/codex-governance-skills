from __future__ import annotations

import json
import unittest
from pathlib import Path

try:
    from .recall_eval import evaluate_case, summarize_cases
except ImportError:  # unittest discovery imports test modules as top-level modules
    from recall_eval import evaluate_case, summarize_cases


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT
SKILL_TEXT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
FINDING_TEXT = (
    SKILL_ROOT / "references" / "finding-judgment-model.md"
).read_text(encoding="utf-8")
RETRIEVAL_TEXT = (
    SKILL_ROOT / "references" / "retrieval-routing.md"
).read_text(encoding="utf-8")
METHOD_TEXT = (
    SKILL_ROOT / "references" / "inquiry-methods.md"
).read_text(encoding="utf-8")
AUTHORITY_TEXT = (
    SKILL_ROOT / "references" / "project-authority-routing.md"
).read_text(encoding="utf-8")
CASES = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "recall_cases.json").read_text(
        encoding="utf-8"
    )
)


class RecallIntegrityContractTests(unittest.TestCase):
    def test_activation_phrase_is_real_utf8_not_mojibake(self) -> None:
        self.assertIn("exact Chinese phrase `三堂会审`", SKILL_TEXT)
        self.assertNotIn("涓夊爞", SKILL_TEXT)

    def test_coverage_ledger_breaks_priority_area_circularity(self) -> None:
        for field in (
            "surface_id",
            "existence_evidence",
            "population_size",
            "inspection_mode",
            "sample_contract",
            "coverage_state",
            "residual_gap",
        ):
            self.assertIn(field, SKILL_TEXT)
        self.assertIn("snapshot equivalence", AUTHORITY_TEXT.lower())
        self.assertIn("discovered material surface", SKILL_TEXT)
        self.assertIn("cannot silently disappear", SKILL_TEXT)

    def test_clues_survive_until_cross_role_fusion(self) -> None:
        for field in (
            "clue_id",
            "exact_locator",
            "redacted_observation",
            "why_unusual",
            "related_clue_ids",
        ):
            self.assertIn(field, FINDING_TEXT)
        for state in ("Open", "Connected", "Promoted", "Explained", "Deferred"):
            self.assertIn(f"`{state}`", FINDING_TEXT)
        self.assertIn("before materiality filtering", FINDING_TEXT)
        self.assertIn("negative-space", FINDING_TEXT)

    def test_retrieval_transport_has_an_executable_completeness_contract(self) -> None:
        for field in (
            "retrieval_scope",
            "expected_count",
            "returned_count",
            "page_count",
            "cursor_state",
            "output_truncated",
            "byte_or_line_range",
            "unread_remainder",
            "completeness_qualification",
        ):
            self.assertIn(field, RETRIEVAL_TEXT)
        self.assertIn("exhaustive claim", RETRIEVAL_TEXT.lower())
        self.assertIn("targeted retrieval", RETRIEVAL_TEXT.lower())

    def test_common_frame_and_context_loss_have_reconciliation_gates(self) -> None:
        for phrase in (
            "independent frame challenge",
            "coverage-ledger difference",
            "scope-only opening brief",
            "same fresh context",
            "checkpoint manifest",
            "synthesis manifest",
            "output_mapping",
        ):
            self.assertIn(phrase, (SKILL_TEXT + FINDING_TEXT).lower())
        self.assertIn("reconcile", SKILL_TEXT.lower())

    def test_lightweight_sentinel_screen_covers_quiet_domains(self) -> None:
        for domain in (
            "security_privacy_and_authorization",
            "reliability_and_recovery",
            "human_factors_accessibility_and_misuse",
            "data_quality_models_and_measurement",
            "dependencies_supply_chain_and_provenance",
            "governance_legal_licensing_and_economics",
            "capacity_cost_and_resources",
            "lifecycle_migration_compatibility_and_external_effects",
        ):
            self.assertIn(domain, METHOD_TEXT)
        self.assertIn("Negative-with-evidence", METHOD_TEXT)
        self.assertIn("Do not run every specialist method", METHOD_TEXT)

    def test_forward_test_corpus_covers_all_planned_failure_surfaces(self) -> None:
        self.assertGreaterEqual(len(CASES), 12)
        case_ids = {case["case_id"] for case in CASES}
        self.assertEqual(len(case_ids), len(CASES))
        required = {
            "activation-utf8",
            "current-state-dirty-override",
            "hidden-subsystem",
            "weak-clue-fusion",
            "cursor-second-page",
            "truncated-long-line",
            "sampling-tail",
            "implicit-private-data",
            "implicit-supply-chain",
            "implicit-model-data",
            "compaction-minority",
            "short-output-manifest",
        }
        self.assertTrue(required.issubset(case_ids))
        for case in CASES:
            self.assertIn(case["severity"], {"medium", "high", "critical"})
            self.assertTrue(case["planted_signals"], case["case_id"])
            self.assertTrue(case["required_detections"], case["case_id"])
            self.assertTrue(case["forbid_complete_when_missing"], case["case_id"])

    def test_evaluator_rejects_false_complete_and_accepts_accounted_run(self) -> None:
        case = next(case for case in CASES if case["case_id"] == "weak-clue-fusion")
        bad = evaluate_case(case, {"detected": [], "domains": [], "completion": "Complete"})
        self.assertFalse(bad.passed)
        self.assertTrue(any("false Complete" in failure for failure in bad.failures))

        good = evaluate_case(
            case,
            {
                "detected": case["required_detections"],
                "domains": case["required_domains"],
                "completion": case["expected_completion"],
            },
        )
        self.assertTrue(good.passed, good.failures)

        for fixture in CASES:
            accounted = evaluate_case(
                fixture,
                {
                    "detected": fixture["required_detections"],
                    "domains": fixture["required_domains"],
                    "completion": fixture["expected_completion"],
                },
            )
            self.assertTrue(accounted.passed, (fixture["case_id"], accounted.failures))

        good_runs = {
            fixture["case_id"]: {
                "detected": fixture["required_detections"],
                "domains": fixture["required_domains"],
                "completion": fixture["expected_completion"],
            }
            for fixture in CASES
        }
        summary = summarize_cases(CASES, good_runs)
        self.assertEqual(summary.passed_count, len(CASES))
        self.assertEqual(summary.severity_weighted_recall, 1.0)
        self.assertEqual(summary.domain_recall, 1.0)
        self.assertEqual(summary.false_complete_count, 0)

        bad_runs = dict(good_runs)
        bad_runs[case["case_id"]] = {
            "detected": [],
            "domains": [],
            "completion": "Complete",
        }
        bad_summary = summarize_cases(CASES, bad_runs)
        self.assertGreater(bad_summary.false_complete_count, 0)
        self.assertLess(bad_summary.severity_weighted_recall, 1.0)


if __name__ == "__main__":
    unittest.main()
