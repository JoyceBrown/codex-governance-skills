import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class LightweightSkillContractTests(unittest.TestCase):
    CONTRACTS = {
        "architecture-health": (
            ("review_status", "boundary_findings", "rollback_risk", "evidence_refs", "next_action", "budget"),
            ("默认只读", "不直接重构"),
        ),
        "capability-director": (
            ("capability_gap", "bounded_candidates", "recommendation", "evidence_refs", "next_action", "budget", "expiry"),
            ("最多三个", "不得自动下载代码"),
        ),
        "diagnose": (
            ("symptom", "reproduction", "hypotheses", "discriminating_check", "root_cause", "evidence_refs", "next_action", "budget"),
            ("至少两项", "不自动修复"),
        ),
        "intent-alignment": (
            ("goal", "visible_success", "scope", "non_goals", "constraints", "intent_status", "unknowns", "evidence_refs", "next_action", "budget"),
            ("不修改代码", "不得从历史摘要补齐用户意图"),
        ),
        "tdd-loop": (
            ("action_status", "execution_status", "review_status", "red", "green", "refactor", "test_evidence", "user_path_result", "evidence_refs", "next_action", "budget"),
            ("只修改用户授权范围", "不能用 `COMPLETED` 掩盖"),
        ),
    }

    def test_each_lightweight_skill_has_stable_output_contract(self):
        for name, (fields, boundaries) in self.CONTRACTS.items():
            with self.subTest(skill=name):
                content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("## Output Contract", content)
                self.assertRegex(content, r"(?s)## Output Contract.*?```json.*?```", name)
                for field in fields:
                    self.assertIn(f'"{field}"', content, field)
                for marker in boundaries:
                    self.assertIn(marker, content, marker)

    def test_contracts_keep_local_boundaries_and_composition_fields(self):
        for name in self.CONTRACTS:
            content = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("composition-v1", content)
            for field in ("evidence_refs", "next_action", "budget"):
                self.assertIn(field, content)
            self.assertRegex(content, r"(?i)(standalone|独立使用|回退)")

    def test_diagnose_requires_competing_hypotheses_and_tdd_separates_user_path(self):
        diagnose = (SKILLS / "diagnose" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("至少两项且必须互相竞争", diagnose)
        tdd = (SKILLS / "tdd-loop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("user_path_result", tdd)
        self.assertIn("UNKNOWN", tdd)


if __name__ == "__main__":
    unittest.main()
