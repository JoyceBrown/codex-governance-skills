from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_project import inspect  # noqa: E402


class ProjectInspectionTests(unittest.TestCase):
    def test_empty_project_has_no_experience_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = inspect(Path(directory), 100)

        self.assertEqual([], result["experience_signals"])

    def test_observable_repository_features_become_matching_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text("{}\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "AGENTS.md").write_text("# Local\n", encoding="utf-8")
            (root / "PLANS.md").write_text("# Plan\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "roadmap.md").write_text("# Roadmap\n", encoding="utf-8")
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("[features]\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "test.yml").write_text(
                "name: test\n",
                encoding="utf-8",
            )

            result = inspect(root, 100)

        self.assertEqual(
            {
                "advanced-codex-surfaces",
                "ci-configured",
                "competing-plans",
                "multiple-manifests",
                "multiple-package-managers",
                "nested-agent-rules",
            },
            set(result["experience_signals"]),
        )

    def test_versioned_plans_roadmaps_and_handoffs_are_inventoried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "ROADMAP_3.0_TO_4.0.md",
                "PRODUCT_RECOVERY_PLAN_2026.md",
                "DEVELOPMENT_HANDOFF_3.6.md",
                "CURRENT_MAINLINE_1_TO_2.md",
            ):
                (root / name).write_text(f"# {name}\n", encoding="utf-8")
            (root / "explanation.md").write_text(
                "# Not a plan\n",
                encoding="utf-8",
            )

            result = inspect(root, 100)

        details = {
            item["path"]: item["kind"]
            for item in result["context_artifacts"]["planning_details"]
        }
        self.assertEqual(
            {
                "CURRENT_MAINLINE_1_TO_2.md": "current",
                "DEVELOPMENT_HANDOFF_3.6.md": "handoff",
                "PRODUCT_RECOVERY_PLAN_2026.md": "plan",
                "ROADMAP_3.0_TO_4.0.md": "roadmap",
            },
            details,
        )
        self.assertIn("competing-plans", result["experience_signals"])
        self.assertNotIn(
            "explanation.md",
            result["context_artifacts"]["planning"],
        )

    def test_truncated_scan_is_explicitly_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(5):
                (root / f"file-{index}.txt").write_text("data\n", encoding="utf-8")

            result = inspect(root, 2)

        self.assertTrue(result["scan"]["truncated"])
        self.assertFalse(result["scan"]["complete"])
        self.assertIn("rerun", result["scan"]["required_follow_up"])

    def test_root_documentation_and_test_configs_are_inventoried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Readme\n", encoding="utf-8")
            (root / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

            result = inspect(root, 100)

        self.assertIn("SECURITY.md", result["context_artifacts"]["docs"])
        self.assertIn("pytest.ini", result["context_artifacts"]["test_configs"])


if __name__ == "__main__":
    unittest.main()
