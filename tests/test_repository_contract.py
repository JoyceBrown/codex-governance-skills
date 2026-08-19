import json
import re
import subprocess
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
COLLECTION_REPOSITORY = "https://github.com/JoyceBrown/codex-governance-skills"
MATURE = {
    "bootstrap-codex-project",
    "durable-context",
    "human-centered-reasoning-guard",
    "deliberate-project",
}
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".yaml", ".yml"}


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
        for name in MATURE:
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

    def test_collection_is_the_only_maintenance_authority(self):
        manifest = json.loads(
            (ROOT / "docs" / "source-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["schema"], "codex-governance-skills-source-manifest-v3"
        )
        self.assertEqual(manifest["authority"]["repository"], COLLECTION_REPOSITORY)
        records = {record["skill"]: record for record in manifest["skills"]}
        self.assertEqual(set(records), MATURE)
        for name, record in records.items():
            self.assertEqual(record["authority_repository"], COLLECTION_REPOSITORY)
            self.assertEqual(record["source_path"], f"skills/{name}")
            self.assertRegex(record["legacy_import"]["commit"], r"^[0-9a-f]{40}$")
            archive_ref = record["legacy_import"]["archive_ref"]
            self.assertEqual(archive_ref, f"refs/tags/legacy/{name}/main")
            archived_commit = subprocess.run(
                ["git", "rev-parse", f"{archive_ref}^{{commit}}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(archived_commit, record["legacy_import"]["commit"])
            self.assertNotEqual(
                record["legacy_import"]["repository"], COLLECTION_REPOSITORY
            )

    def test_mature_skill_regressions_are_embedded(self):
        for name in ("bootstrap-codex-project", "durable-context", "deliberate-project"):
            tests = list((SKILLS / name / "tests").glob("test_*.py"))
            self.assertTrue(tests, name)
        self.assertTrue(
            (SKILLS / "durable-context" / "scripts" / "audit_skill_collection.py").is_file()
        )
        self.assertTrue(
            (
                SKILLS
                / "human-centered-reasoning-guard"
                / "scripts"
                / "run-regression-tests.ps1"
            ).is_file()
        )

    def test_git_paths_and_published_text_blobs_are_portable(self):
        paths = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        tracked = [path.decode("utf-8") for path in paths if path]
        self.assertTrue(tracked)
        for path in tracked:
            self.assertNotIn("\\", path)
            self.assertFalse(path.startswith("/"))
            if Path(path).suffix.lower() not in TEXT_SUFFIXES and Path(path).name not in {
                ".gitattributes",
                ".gitignore",
            }:
                continue
            blob = subprocess.run(
                ["git", "show", f":{path}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertFalse(blob.startswith(b"\xef\xbb\xbf"), path)
            self.assertNotIn(b"\r\n", blob, path)
            blob.decode("utf-8", errors="strict")

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
