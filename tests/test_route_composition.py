import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "route-composition.py"
spec = importlib.util.spec_from_file_location("route_composition", SCRIPT)
router = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(router)


class CompositionRouteTests(unittest.TestCase):
    def test_explicit_pao_has_priority_and_bounded_helpers(self):
        result = router.route({"explicit_skill": "project-agent-orchestrator", "signals": ["long_running", "authorized_code_change"]})
        self.assertEqual(result["primary_skill"], "project-agent-orchestrator")
        self.assertEqual(result["collaborators"], ["durable-context", "tdd-loop"])
        self.assertLessEqual(len(result["collaborators"]), 2)

    def test_ambiguous_goal_routes_to_intent_before_code_work(self):
        result = router.route({"signals": ["ambiguous_goal", "authorized_code_change"]})
        self.assertEqual(result["primary_skill"], "intent-alignment")
        self.assertEqual(result["collaborators"], [])
        self.assertEqual(result["degradation"], "standalone")

    def test_failure_with_environment_signal_keeps_diagnose_primary(self):
        result = router.route({"signals": ["failure", "windows_risk", "authorized_code_change"]})
        self.assertEqual(result["primary_skill"], "diagnose")
        self.assertEqual(result["collaborators"], ["execution-reliability", "tdd-loop"])

    def test_no_signal_is_explicitly_unknown_and_stateless(self):
        result = router.route({})
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["primary_skill"])
        self.assertEqual(result["collaborators"], [])

    def test_unknown_explicit_skill_is_rejected(self):
        with self.assertRaises(ValueError):
            router.route({"explicit_skill": "not-a-skill"})


if __name__ == "__main__":
    unittest.main()
