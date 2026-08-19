import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {
    "bootstrap-codex-project",
    "durable-context",
    "human-centered-reasoning-guard",
    "deliberate-project",
    "intent-alignment",
    "diagnose",
    "tdd-loop",
    "architecture-health",
    "capability-director",
}


class IntegratedRepositoryContractTests(unittest.TestCase):
    def test_exact_skill_set_and_entrypoints(self):
        actual = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual(actual, EXPECTED)
        for name in EXPECTED:
            skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(skill, r"(?m)^---\s*$")
            self.assertRegex(skill, rf"(?m)^name:\s*{re.escape(name)}\s*$")
            self.assertRegex(skill, r"(?m)^description:\s*.+$")

    def test_composition_contracts_are_present(self):
        for name in EXPECTED - {"intent-alignment", "diagnose", "tdd-loop", "architecture-health", "capability-director"}:
            skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Composition Contract", skill)
        composition = (ROOT / "docs" / "composition.md").read_text(encoding="utf-8")
        for field in ("request_id", "status", "scope", "evidence_refs", "next_action", "budget"):
            self.assertIn(field, composition)

    def test_ui_metadata_matches_skill_names(self):
        for name in EXPECTED:
            metadata = (SKILLS / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn("display_name:", metadata)
            self.assertIn("short_description:", metadata)

    def test_public_tree_excludes_private_runtime_material(self):
        forbidden_names = {".agent-context", "hook-events.jsonl", "conversation-history.md", ".runtime", ".git"}
        for path in ROOT.rglob("*"):
            lowered = {part.lower() for part in path.relative_to(ROOT).parts}
            if ".git" in lowered:
                continue
            self.assertTrue(forbidden_names.isdisjoint(lowered), str(path))
        content_files = [
            p for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".sqlite3"}
        ]
        forbidden_values = re.compile(r"(?:C:\\Users\\JIE|E:\\AI Project|gho_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{20,})", re.I)
        for path in content_files:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(forbidden_values.search(text), str(path))

    def test_capability_director_is_read_only_and_bounded(self):
        skill = (SKILLS / "capability-director" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("最多比较 3 个候选", skill)
        self.assertIn("不得自动下载代码", skill)
        self.assertIn("Capability Receipt", skill)


if __name__ == "__main__":
    unittest.main()
