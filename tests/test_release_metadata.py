import importlib.util
import unittest


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "validate_release_metadata", ROOT / "scripts" / "validate-release-metadata.py"
)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class ReleaseMetadataTests(unittest.TestCase):
    def test_protected_contract_change_requires_both_metadata_files(self):
        changed = ["scripts/validate-artifacts.py", "docs/composition.md"]
        self.assertEqual(validator.metadata_gaps(changed), ["CHANGELOG.md", "VERSION"])

    def test_metadata_pair_is_sufficient_for_protected_change(self):
        changed = ["schemas/artifact.schema.json", "VERSION", "CHANGELOG.md"]
        self.assertEqual(validator.metadata_gaps(changed), [])

    def test_unrelated_change_does_not_require_release_metadata(self):
        self.assertEqual(validator.metadata_gaps(["examples/diagnose/competing-hypotheses.json"]), [])

    def test_skill_entrypoint_is_protected(self):
        self.assertTrue(validator.is_protected("skills/diagnose/SKILL.md"))
        self.assertFalse(validator.is_protected("skills/diagnose/tests/test_contract_examples.py"))


if __name__ == "__main__":
    unittest.main()
