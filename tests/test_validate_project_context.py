from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_project_context import validate  # noqa: E402


ACTIVE_PLAN = """# Active Execution Plan

plan_id: FEATURE-01
status: active
authority: exclusive
current_task_id: TASK-01
latest_change_id: CHANGE-01
latest_change_class: task_adjustment
change_authority_reference: none
on_complete: wait

## Allowed scope

Implement TASK-01.

## Excluded scope

Do not start other roadmap work.

## Milestones

| Task ID | Status | Outcome |
| --- | --- | --- |
| TASK-01 | in_progress | The feature works. |

## Validation

Run the relevant test suite.
"""

AGENT_ROUTING = """# Instructions

Use PLANS.md only. The roadmap and docs/work/current.md do not authorize work.
Classify changes as task_adjustment, priority_branch, or roadmap_change.
A subagent may not broaden scope or select roadmap work without explicit authority.
"""


class PlanningAuthorityValidationTests(unittest.TestCase):
    def make_project(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
        return temporary, root

    @staticmethod
    def codes(result: dict[str, object], group: str) -> set[str]:
        entries = result[group]
        assert isinstance(entries, list)
        return {str(entry["code"]) for entry in entries}

    def test_minimal_project_does_not_require_planning_artifacts(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)

        result = validate(root, "minimal")

        self.assertTrue(result["ok"])
        self.assertEqual(set(), self.codes(result, "errors"))

    def test_valid_planning_authority_module_passes(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        (root / "PLANS.md").write_text(ACTIVE_PLAN, encoding="utf-8")
        (root / "docs" / "work").mkdir(parents=True)
        (root / "docs" / "roadmap.md").write_text(
            "# Roadmap\n\nexecution_authority: none\n",
            encoding="utf-8",
        )
        (root / "docs" / "work" / "current.md").write_text(
            "# Current Work\n\nrecord_kind: checkpoint\nexecution_authority: none\nactive_plan: ../../PLANS.md\n",
            encoding="utf-8",
        )

        result = validate(root, "minimal")

        self.assertTrue(result["ok"])
        self.assertEqual(set(), self.codes(result, "errors"))

    def test_multiple_active_plans_fail(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\n\nUse PLANS.md as the active plan.\n",
            encoding="utf-8",
        )
        (root / "PLANS.md").write_text(ACTIVE_PLAN, encoding="utf-8")
        (root / "docs").mkdir()
        second = ACTIVE_PLAN.replace("FEATURE-01", "FEATURE-02").replace("TASK-01", "TASK-02")
        (root / "docs" / "plan.md").write_text(second, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("multiple-active-plans", self.codes(result, "errors"))

    def test_ambiguous_completion_action_fails(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\n\nUse PLANS.md as the active plan.\n",
            encoding="utf-8",
        )
        plan = ACTIVE_PLAN.replace("on_complete: wait", "on_complete: continue the roadmap")
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("ambiguous-on-complete", self.codes(result, "errors"))

    def test_active_plan_must_use_canonical_root_path(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\n\nUse PLANS.md as the active plan.\n",
            encoding="utf-8",
        )
        (root / "docs").mkdir()
        (root / "docs" / "plan.md").write_text(ACTIVE_PLAN, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("active-plan-not-canonical", self.codes(result, "errors"))

    def test_undeclared_roadmap_authority_fails_with_active_plan(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\n\nUse PLANS.md only. The roadmap does not authorize work.\n",
            encoding="utf-8",
        )
        (root / "PLANS.md").write_text(ACTIVE_PLAN, encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs" / "roadmap.md").write_text("# Roadmap\n", encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("roadmap-authority-undeclared", self.codes(result, "errors"))

    def test_checkpoint_cannot_claim_execution_authority(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "docs" / "work").mkdir(parents=True)
        (root / "docs" / "work" / "current.md").write_text(
            "# Current Work\n\nrecord_kind: checkpoint\nexecution_authority: exclusive\n",
            encoding="utf-8",
        )

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("checkpoint-has-execution-authority", self.codes(result, "errors"))

    def test_roadmap_checklist_warns_without_forcing_strict_mode(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "docs").mkdir()
        (root / "docs" / "roadmap.md").write_text(
            "# Roadmap\n\n- [ ] Build search\n",
            encoding="utf-8",
        )

        result = validate(root, "minimal")

        self.assertTrue(result["ok"])
        warning_codes = self.codes(result, "warnings")
        self.assertIn("roadmap-authority-undeclared", warning_codes)
        self.assertIn("actionable-roadmap-checklist", warning_codes)

    def test_priority_branch_requires_deferred_work_details(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace(
            "latest_change_class: task_adjustment",
            "latest_change_class: priority_branch",
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        error_codes = self.codes(result, "errors")
        self.assertIn("priority-branch-without-deferred-work", error_codes)
        self.assertIn("incomplete-priority-branch-record", error_codes)

    def test_valid_priority_branch_passes(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace(
            "latest_change_class: task_adjustment",
            "latest_change_class: priority_branch",
        ).replace(
            "## Milestones",
            "## Deferred work\n\n| Item | Reason deferred | Impact | Resume condition |\n"
            "| --- | --- | --- | --- |\n"
            "| TASK-OLD | User changed priority | Delays login | After TASK-01 review |\n\n"
            "## Milestones",
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertTrue(result["ok"])
        self.assertEqual(set(), self.codes(result, "errors"))

    def test_roadmap_change_requires_durable_authority_reference(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace(
            "latest_change_class: task_adjustment",
            "latest_change_class: roadmap_change",
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn(
            "roadmap-change-without-authority-reference",
            self.codes(result, "errors"),
        )

    def test_roadmap_change_with_durable_reference_passes(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace(
            "latest_change_class: task_adjustment",
            "latest_change_class: roadmap_change",
        ).replace(
            "change_authority_reference: none",
            "change_authority_reference: docs/product.md#scope",
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertTrue(result["ok"])

    def test_active_plan_requires_change_and_subagent_routing(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\n\nUse PLANS.md as the active plan.\n",
            encoding="utf-8",
        )
        (root / "PLANS.md").write_text(ACTIVE_PLAN, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        error_codes = self.codes(result, "errors")
        self.assertIn("missing-requirement-change-routing", error_codes)
        self.assertIn("missing-subagent-authority-routing", error_codes)

    def test_active_plan_requires_change_classification_metadata(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace("latest_change_id: CHANGE-01\n", "").replace(
            "latest_change_class: task_adjustment\n", ""
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn("incomplete-active-plan", self.codes(result, "errors"))

    def test_invalid_change_class_fails(self) -> None:
        temporary, root = self.make_project()
        self.addCleanup(temporary.cleanup)
        (root / "AGENTS.md").write_text(AGENT_ROUTING, encoding="utf-8")
        plan = ACTIVE_PLAN.replace(
            "latest_change_class: task_adjustment",
            "latest_change_class: quick_fix",
        )
        (root / "PLANS.md").write_text(plan, encoding="utf-8")

        result = validate(root, "minimal")

        self.assertFalse(result["ok"])
        self.assertIn(
            "invalid-requirement-change-class",
            self.codes(result, "errors"),
        )


if __name__ == "__main__":
    unittest.main()
