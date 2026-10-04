import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class DiagnoseContractTests(unittest.TestCase):
    def test_example_has_competing_hypotheses_and_check(self):
        example = json.loads((ROOT / "examples/diagnose/competing-hypotheses.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(example["hypotheses"]), 2)
        self.assertTrue(example["discriminating_check"])

    def test_reference_has_bounded_stop_rule(self):
        text = (Path(__file__).parents[1] / "references/contract-examples.md").read_text(encoding="utf-8")
        self.assertIn("连续失败两次", text)
        self.assertIn("独立回退", text)


if __name__ == "__main__":
    unittest.main()
