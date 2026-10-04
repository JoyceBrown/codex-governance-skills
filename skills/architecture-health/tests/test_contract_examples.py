import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ArchitectureHealthContractTests(unittest.TestCase):
    def test_example_does_not_turn_unknown_into_a_structural_change(self):
        example = json.loads((ROOT / "examples/architecture-health/boundary-unknown.json").read_text(encoding="utf-8"))
        self.assertEqual(example["review_status"], "OPEN")
        self.assertEqual(example["rollback_risk"], "UNKNOWN")
        self.assertTrue(example["next_action"])

    def test_reference_requires_evidence_and_reversal(self):
        text = (Path(__file__).parents[1] / "references/contract-examples.md").read_text(encoding="utf-8")
        self.assertIn("逆转条件", text)
        self.assertIn("不直接重构", text)


if __name__ == "__main__":
    unittest.main()
