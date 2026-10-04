import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate-composition.py"
spec = importlib.util.spec_from_file_location("validate_composition", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def envelope(**overrides):
    value = {
        "schema_version": "composition-v1",
        "request_id": "r1",
        "parent_request_id": None,
        "source_skill": "intent-alignment",
        "target_skill": "diagnose",
        "scope": "current task",
        "claim_kind": "observed",
        "intent_status": "DECIDED",
        "recovery_status": "FOUND",
        "action_status": "READY",
        "review_status": "OPEN",
        "execution_status": "IN_PROGRESS",
        "outcome_status": "OPEN",
        "authority_owner": "intent_summary",
        "side_effect": "none",
        "evidence_refs": ["alignment-1"],
        "next_action": "run one check",
        "degradation": "composed",
        "budget": {"chars": 1000, "calls": 2, "depth": 2, "spent_chars": 0, "spent_calls": 0},
        "lifecycle": "running",
    }
    value.update(overrides)
    return value


class CompositionProtocolTests(unittest.TestCase):
    def test_valid_composed_envelope(self):
        self.assertEqual(validator.validate_envelope(envelope())["request_id"], "r1")

    def test_standalone_must_not_claim_another_target(self):
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(degradation="standalone"))

    def test_unknown_generic_status_is_rejected(self):
        value = envelope()
        value["status"] = "READY"
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(value)

    def test_blocked_action_cannot_be_completed(self):
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(
                envelope(action_status="BLOCKED", execution_status="COMPLETED")
            )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(execution_status="COMPLETED", lifecycle="running"))
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(action_status="BLOCKED", lifecycle="running"))
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(degradation="blocked", lifecycle="running"))

    def test_budget_and_lifecycle_are_bounded(self):
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(budget={"chars": 9000, "calls": 1, "depth": 1}))
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_lifecycle_transition("completed", "running")
        validator.validate_lifecycle_transition("waiting", "resumed")
        validator.validate_lifecycle_history(["created", "routed", "running", "partial", "completed"])
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_lifecycle_history(["created", "completed", "running"])

    def test_route_authority_and_side_effect_boundaries(self):
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(
                envelope(source_skill="intent-alignment", target_skill="tdd-loop")
            )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(envelope(authority_owner="root_cause_evidence"))
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(
                envelope(source_skill="intent-alignment", target_skill="diagnose", side_effect="project_write")
            )

    def test_external_write_requires_guard_and_chain_budget_is_cumulative(self):
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_envelope(
                envelope(
                    source_skill="execution-reliability",
                    target_skill="execution-reliability",
                    authority_owner="execution_evidence",
                    side_effect="external_write",
                    degradation="standalone",
                )
            )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([
                envelope(
                    source_skill="execution-reliability",
                    target_skill="execution-reliability",
                    authority_owner="execution_evidence",
                    side_effect="external_write",
                    degradation="standalone",
                    budget={"chars": 1000, "calls": 1, "depth": 0, "spent_chars": 100, "spent_calls": 1},
                )
            ])
        root = envelope(
            budget={"chars": 100, "calls": 1, "depth": 2, "spent_chars": 80, "spent_calls": 1},
        )
        child = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="diagnose",
            target_skill="tdd-loop",
            authority_owner="root_cause_evidence",
            budget={"chars": 80, "calls": 1, "depth": 2, "spent_chars": 30, "spent_calls": 0},
        )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([root, child])

    def test_chain_rejects_wrong_child_owner_or_fanout(self):
        root = envelope(
            source_skill="intent-alignment",
            target_skill="diagnose",
            authority_owner="intent_summary",
            budget={"chars": 3000, "calls": 4, "depth": 2, "spent_chars": 10, "spent_calls": 0},
        )
        wrong_owner = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="tdd-loop",
            target_skill="diagnose",
            authority_owner="code_test_verification",
            budget={"chars": 1000, "calls": 1, "depth": 2, "spent_chars": 10, "spent_calls": 0},
        )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([root, wrong_owner])
        children = [
            envelope(
                request_id=f"r{i}",
                parent_request_id="r1",
                source_skill="diagnose",
                target_skill="tdd-loop",
                authority_owner="root_cause_evidence",
                budget={"chars": 1000, "calls": 1, "depth": 2, "spent_chars": 10, "spent_calls": 0},
            )
            for i in (2, 3, 4)
        ]
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([root, *children])

    def test_sibling_budget_allocations_cannot_overcommit_parent(self):
        root = envelope(
            target_skill="diagnose",
            budget={"chars": 1000, "calls": 4, "depth": 2, "spent_chars": 0, "spent_calls": 0},
        )
        children = [
            envelope(
                request_id=f"r{i}",
                parent_request_id="r1",
                source_skill="diagnose",
                target_skill=target,
                authority_owner="root_cause_evidence",
                budget={"chars": 600, "calls": 1, "depth": 2, "spent_chars": 100, "spent_calls": 0},
            )
            for i, target in ((2, "tdd-loop"), (3, "execution-reliability"))
        ]
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([root, *children])

    def test_completed_request_cannot_have_an_active_descendant(self):
        parent = envelope(
            target_skill="diagnose",
            execution_status="COMPLETED",
            lifecycle="completed",
            budget={"chars": 3000, "calls": 4, "depth": 2, "spent_chars": 100, "spent_calls": 1},
        )
        child = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="diagnose",
            target_skill="tdd-loop",
            authority_owner="root_cause_evidence",
            budget={"chars": 1000, "calls": 2, "depth": 2, "spent_chars": 100, "spent_calls": 1},
        )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([parent, child])

    def test_valid_two_level_chain(self):
        first = envelope()
        second = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="diagnose",
            target_skill="tdd-loop",
            authority_owner="root_cause_evidence",
            budget={"chars": 900, "calls": 2, "depth": 2, "spent_chars": 100, "spent_calls": 1},
        )
        self.assertEqual(len(validator.validate_chain([first, second])), 2)

    def test_known_collaboration_profiles_are_bounded(self):
        profiles = [
            (
                envelope(
                    source_skill="durable-context",
                    target_skill="project-agent-orchestrator",
                    authority_owner="continuity_ledger",
                    budget={"chars": 1000, "calls": 3, "depth": 2, "spent_chars": 100, "spent_calls": 1},
                ),
                envelope(
                    request_id="r2",
                    parent_request_id="r1",
                    source_skill="project-agent-orchestrator",
                    target_skill="tdd-loop",
                    authority_owner="current_session_execution",
                    budget={"chars": 800, "calls": 1, "depth": 2, "spent_chars": 100, "spent_calls": 1},
                ),
            ),
            (
                envelope(
                    source_skill="execution-reliability",
                    target_skill="human-centered-reasoning-guard",
                    authority_owner="execution_evidence",
                    budget={"chars": 1000, "calls": 3, "depth": 2, "spent_chars": 100, "spent_calls": 1},
                ),
                envelope(
                    request_id="r2",
                    parent_request_id="r1",
                    source_skill="human-centered-reasoning-guard",
                    target_skill="human-centered-reasoning-guard",
                    authority_owner="authorization_and_completion_gate",
                    budget={"chars": 800, "calls": 1, "depth": 2, "spent_chars": 100, "spent_calls": 1},
                ),
            ),
        ]
        for first, second in profiles:
            self.assertEqual(len(validator.validate_chain([first, second])), 2)

    def test_chain_rejects_cycle_and_missing_parent(self):
        first = envelope(parent_request_id="r2")
        second = envelope(request_id="r2", parent_request_id="r1")
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([first, second])
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([envelope(parent_request_id="missing")])

    def test_chain_rejects_guard_block_override(self):
        guard = envelope(
            source_skill="human-centered-reasoning-guard",
            target_skill="diagnose",
            authority_owner="authorization_and_completion_gate",
            action_status="BLOCKED",
            execution_status="UNKNOWN",
            degradation="composed",
            lifecycle="blocked",
        )
        child = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="diagnose",
            target_skill="tdd-loop",
            authority_owner="root_cause_evidence",
        )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([guard, child])

        middle = envelope(
            request_id="r2",
            parent_request_id="r1",
            source_skill="diagnose",
            target_skill="diagnose",
            authority_owner="root_cause_evidence",
            action_status="PARTIAL",
            execution_status="IN_PROGRESS",
            degradation="composed",
            budget={"chars": 900, "calls": 1, "depth": 2, "spent_chars": 100, "spent_calls": 1},
        )
        grandchild = envelope(
            request_id="r3",
            parent_request_id="r2",
            source_skill="diagnose",
            target_skill="tdd-loop",
            authority_owner="root_cause_evidence",
            budget={"chars": 800, "calls": 0, "depth": 2, "spent_chars": 100, "spent_calls": 0},
        )
        with self.assertRaises(validator.CompositionValidationError):
            validator.validate_chain([guard, middle, grandchild])


if __name__ == "__main__":
    unittest.main()
