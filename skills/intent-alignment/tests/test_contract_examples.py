import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class IntentAlignmentContractTests(unittest.TestCase):
    def test_ambiguous_goal_example_preserves_open_intent(self):
        example = json.loads((ROOT / "examples/intent-alignment/ambiguous-goal.json").read_text(encoding="utf-8"))
        self.assertEqual(example["artifact_kind"], "receipt")
        self.assertEqual(example["expected"]["intent_status"], "OPEN")
        self.assertIsNotNone(example["next_action"])

    def test_reference_keeps_inference_and_scope_boundary(self):
        text = (Path(__file__).parents[1] / "references/contract-examples.md").read_text(encoding="utf-8")
        for marker in ("最多三个", "CONFLICTED", "独立回退"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
