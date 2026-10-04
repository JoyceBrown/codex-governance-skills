import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class TddContractTests(unittest.TestCase):
    def test_example_separates_execution_and_user_path(self):
        example = json.loads((ROOT / "examples/tdd-loop/user-path-unknown.json").read_text(encoding="utf-8"))
        self.assertEqual(example["execution_status"], "COMPLETED")
        self.assertEqual(example["user_path_result"], "UNKNOWN")
        self.assertEqual(example["status"], "partial")

    def test_reference_keeps_external_result_unknown(self):
        text = (Path(__file__).parents[1] / "references/contract-examples.md").read_text(encoding="utf-8")
        self.assertIn("用户路径仍是 `UNKNOWN`", text)
        self.assertIn("不自动安装陌生依赖", text)


if __name__ == "__main__":
    unittest.main()
