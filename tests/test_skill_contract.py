from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "deliberate-project"
SKILL_TEXT = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
ROUTING_TEXT = (
    SKILL_ROOT / "references" / "retrieval-routing.md"
).read_text(encoding="utf-8")
AGENT_TEXT = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
ALL_CONTRACT_TEXT = SKILL_TEXT + ROUTING_TEXT


class SkillContractTests(unittest.TestCase):
    def test_core_skill_stays_within_progressive_disclosure_budget(self) -> None:
        self.assertLessEqual(len(SKILL_TEXT.splitlines()), 500)
        words = re.findall(r"\b[\w-]+\b", SKILL_TEXT, flags=re.UNICODE)
        self.assertLessEqual(len(words), 5000)

    def test_explicit_activation_is_aligned_across_metadata(self) -> None:
        self.assertIn("Proceed only when", SKILL_TEXT)
        self.assertRegex(
            AGENT_TEXT, r"(?m)^\s*allow_implicit_invocation:\s*false\s*$"
        )
        self.assertNotRegex(
            AGENT_TEXT, r"(?m)^\s*allow_implicit_invocation:\s*true\s*$"
        )

    def test_every_routed_reference_exists(self) -> None:
        references = set(re.findall(r"references/([A-Za-z0-9._-]+\.md)", SKILL_TEXT))
        self.assertTrue(references)
        missing = [
            name for name in sorted(references)
            if not (SKILL_ROOT / "references" / name).is_file()
        ]
        self.assertEqual(missing, [])

    def test_investigation_priority_and_hard_boundaries_are_explicit(self) -> None:
        for phrase in (
            "Maximize expected decision-relevant evidence value",
            "Safety controls route the investigation",
            "Apply only these hard boundaries",
            "Missing non-boundary metadata qualifies evidence",
            "Prefer a qualified lead over an unexamined gap",
        ):
            self.assertIn(phrase, ALL_CONTRACT_TEXT)
        self.assertNotIn("Apply these hard filters first", ALL_CONTRACT_TEXT)

    def test_provider_contract_cannot_capture_parent_routing(self) -> None:
        for phrase in (
            "intersection of the current user request",
            "does not set global tool priority",
            "general orchestration or fallback preferences as non-governing",
            "parent router may automatically select another",
        ):
            self.assertIn(phrase, ROUTING_TEXT)
        self.assertNotIn("follow AnySearch's own fallback-approval rule", ROUTING_TEXT)

    def test_boundary_matrix_preserves_inquiry_quality(self) -> None:
        scenarios = {
            "Authorized public, non-sensitive, read-only search": "Proceed automatically",
            "alternative stays in the same public read-only boundary": "Fallback automatically",
            "send private or restricted material": "ask before expansion",
            "authenticated/private state not already in scope": "Ask before crossing the boundary",
            "disposable isolated diagnostic": "Run the bounded isolated check",
            "Authenticated browser has unknown material incidental effects": "do not load while unknown",
        }
        for situation, action in scenarios.items():
            row = next(
                (line for line in ROUTING_TEXT.splitlines() if situation in line),
                "",
            )
            self.assertIn(action, row, situation)

    def test_retrieval_audit_is_redacted_and_reproducible(self) -> None:
        for field in (
            "request_time",
            "sensitivity_class",
            "redacted_query_or_parameter_digest",
            "source_origin_and_lineage",
            "result_fingerprint",
            "route_qualification",
            "source_evidence_grade",
        ):
            self.assertIn(field, ROUTING_TEXT)
        self.assertIn("Do not log secrets, raw private queries", ROUTING_TEXT)
        self.assertIn("Classify the outbound query payload", ROUTING_TEXT)
        self.assertIn("derived clues may reveal a private project", ROUTING_TEXT)
        self.assertIn("Grade an opened original source independently", ROUTING_TEXT)

    def test_role_isolation_and_completion_states_are_not_prompt_only_claims(self) -> None:
        for phrase in (
            "fork_turns=none",
            "project writes, experience-catalog operations, centralized verification",
            "every discovered material surface and priority area is coverage-closed",
            "whose material surface is silently absent",
            "required role contribution",
            "only material source remains inaccessible",
            "transport completeness is unknown",
        ):
            self.assertIn(phrase, SKILL_TEXT)

    def test_operation_consent_and_isolation_states_are_unambiguous(self) -> None:
        self.assertIn("that exact operation and data scope", ROUTING_TEXT)
        self.assertIn("requirements remain binding only if the fallback invokes another AnySearch operation", ROUTING_TEXT)
        self.assertIn("isolated stateful behavior, containment", SKILL_TEXT)
        self.assertIn("User agreement alone does not turn unknown external state changes", ROUTING_TEXT)

    def test_experience_independence_requires_case_and_lineage(self) -> None:
        self.assertIn("distinct cases from materially independent", SKILL_TEXT)
        self.assertIn("non-overlapping declared source lineages", SKILL_TEXT)

    def test_current_read_only_instruction_overrides_catalog_configuration(self) -> None:
        self.assertIn("current request does not prohibit persistence", SKILL_TEXT)
        self.assertIn("never overrides the current user's read-only", SKILL_TEXT)


if __name__ == "__main__":
    unittest.main()
