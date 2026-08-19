import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import audit_skill_collection as audit


VALID_SKILL = """---\nname: {name}\ndescription: A test skill for the audit fixture.\n---\n\n# Test\n"""


class SkillCollectionAuditTests(unittest.TestCase):
    def write(self, path: Path, content: str | bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")

    def test_normalised_source_install_match_and_runtime_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            install = root / "install"
            self.write(source / "alpha" / "SKILL.md", VALID_SKILL.format(name="alpha").replace("\n", "\r\n"))
            self.write(source / "alpha" / "scripts" / "run.py", "print('ok')\n")
            self.write(install / "alpha" / "SKILL.md", VALID_SKILL.format(name="alpha"))
            self.write(install / "alpha" / "scripts" / "run.py", "print('ok')\n")
            self.write(install / "alpha" / "runtime.conf", "Runtime: Python\nCommand: python <skill_dir>/scripts/run.py\n")
            report = audit.audit(install_root=install, source_roots=[source], validator_path=Path("does-not-exist"))
            self.assertEqual(report["status"], "warning")
            self.assertEqual([item["status"] for item in report["comparisons"] if item["name"] == "alpha"], ["match"])
            self.assertFalse(any(item["code"] == "RUNTIME_TARGET_MISSING" for item in report["issues"]))

    def test_duplicate_invalid_stale_active_and_missing_runtime_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = root / "install"
            source = root / "source"
            self.write(install / "one" / "SKILL.md", VALID_SKILL.format(name="duplicate"))
            self.write(install / "two" / "SKILL.md", VALID_SKILL.format(name="duplicate"))
            self.write(install / "bad" / "SKILL.md", "not frontmatter\n")
            self.write(install / "one" / "runtime.conf", "Runtime: Python\nCommand: python <skill_dir>/scripts/missing.py\n")
            self.write(source / "source-only" / "SKILL.md", VALID_SKILL.format(name="source-only"))
            hooks = root / "hooks.json"
            self.write(hooks, json.dumps({"hooks": [{"command": r"py C:\Users\Example\.codex\skills\old\hook.py"}]}))
            report = audit.audit(install_root=install, source_roots=[source], hooks_path=hooks, validator_path=Path("does-not-exist"))
            codes = {item["code"] for item in report["issues"]}
            self.assertEqual(report["status"], "fail")
            self.assertIn("DUPLICATE_SKILL_NAME", codes)
            self.assertIn("FRONTMATTER_NAME_MISMATCH", codes)
            self.assertIn("STALE_ACTIVE_PATH", codes)
            self.assertIn("RUNTIME_TARGET_MISSING", codes)

    def test_historical_old_path_is_warning_not_active_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = root / "install"
            self.write(install / "alpha" / "SKILL.md", VALID_SKILL.format(name="alpha"))
            self.write(install / "alpha" / "docs" / "history.md", r"Old path C:\Users\Example\.codex\skills\alpha")
            report = audit.audit(install_root=install, validator_path=Path("does-not-exist"))
            self.assertEqual(report["status"], "warning")
            self.assertTrue(any(item["code"] == "STALE_HISTORICAL_PATH" for item in report["issues"]))

    def test_source_skill_inherits_containing_collection_git_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repository = root / "collection"
            source = repository / "skills"
            install = root / "install"
            self.write(source / "alpha" / "SKILL.md", VALID_SKILL.format(name="alpha"))
            self.write(install / "alpha" / "SKILL.md", VALID_SKILL.format(name="alpha"))
            subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "Audit Fixture"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "audit@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-m", "fixture"], check=True, capture_output=True)

            report = audit.audit(install_root=install, source_roots=[source], validator_path=Path("does-not-exist"))
            source_record = next(item for item in report["skills"]["source"] if item["name"] == "alpha")
            self.assertEqual(source_record["git"]["path"], str(repository.resolve()))
            self.assertEqual(source_record["git"]["scope"], "containing_worktree")
            self.assertEqual(source_record["git"]["skill_path"], "skills/alpha")
            self.assertEqual(source_record["git"]["branch"], "main")
            self.assertFalse(source_record["git"]["dirty"])
            self.assertRegex(source_record["git"]["head"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
