import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("artifact_validator", ROOT / "scripts" / "validate-artifacts.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def artifact(**overrides):
    value = {
        "artifact_kind": "receipt", "schema_version": "artifact-v1",
        "status": "COMPLETED", "run_mode": "standalone",
        "evidence_refs": ["test-1"], "next_action": None,
        "budget": {"chars": 1000, "calls": 1, "depth": 0},
    }
    value.update(overrides)
    return value


class ArtifactValidatorTests(unittest.TestCase):
    def test_valid_receipt(self):
        self.assertEqual(validator.validate_artifact(artifact())["status"], "COMPLETED")

    def test_pao_lowercase_receipt_status_is_accepted(self):
        self.assertEqual(validator.validate_artifact(artifact(status="completed"))["status"], "completed")

    def test_receipt_status_is_skill_owned_and_bounded(self):
        value = artifact(status="domain-specific:accepted")
        self.assertEqual(validator.validate_artifact(value)["status"], "domain-specific:accepted")
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_artifact(artifact(status=" "))
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_artifact(artifact(status="x" * 65))

    def test_checkpoint_requires_recovery_status(self):
        with self.assertRaises(validator.ArtifactValidationError):
            validator.validate_artifact(artifact(artifact_kind="checkpoint", checkpoint_id="c1", task_id="t1"))


if __name__ == "__main__":
    unittest.main()
