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


if __name__ == "__main__":
    unittest.main()
