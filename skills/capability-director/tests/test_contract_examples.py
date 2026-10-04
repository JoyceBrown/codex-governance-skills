import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class CapabilityDirectorContractTests(unittest.TestCase):
    def test_example_keeps_capability_gap_as_a_recommendation(self):
        example = json.loads((ROOT / "examples/capability-director/capability-gap.json").read_text(encoding="utf-8"))
        self.assertEqual(example["capability_gap"], "shared_endpoint")
        self.assertEqual(example["recommendation"], "report-capability-gap")

    def test_reference_forbids_automatic_install(self):
        text = (Path(__file__).parents[1] / "references/contract-examples.md").read_text(encoding="utf-8")
        self.assertIn("不会自动安装", text)
        self.assertIn("最多比较三个", text)


if __name__ == "__main__":
    unittest.main()
