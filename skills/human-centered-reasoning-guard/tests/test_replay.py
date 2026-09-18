"""Behavior regressions for bounded, scope-safe historical replay.

Set HCR_REPLAY_ROOT to another package root to replay these cases against a
baseline. The adapter omits API keywords the old evaluator did not support;
the tests still demand the same observable boundaries and ranking behavior.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(os.environ.get("HCR_REPLAY_ROOT", Path(__file__).resolve().parents[1]))
SPEC = importlib.util.spec_from_file_location("hcr_evaluator_under_test", ROOT / "replay" / "evaluator.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
PARAMETERS = inspect.signature(MODULE.evaluate).parameters


def node(node_id="good", **changes):
    value = {
        "node_id": node_id,
        "goal": {"why": "recover work", "what": "continue the right task"},
        "action": "verify and restore binding",
        "result": "success",
        "goal_progress": 0.8,
        "scope": {"project_id": "project-a", "environment_scope": "candidate"},
        "status": "active",
        "evidence_refs": ["observation-1"],
        "constraints": ["preserve user data"],
        "risk": "low",
        "execution_cost": {"llm_calls": 0, "tool_calls": 1},
    }
    value.update(changes)
    return value


def request(nodes=None, **changes):
    value = {
        "why": "recover work",
        "what": "continue the right task",
        "project_id": "project-a",
        "environment_scope": "candidate",
        "constraints": ["preserve user data"],
        "experience_nodes": [node()] if nodes is None else nodes,
    }
    value.update(changes)
    return value


def evaluate(nodes=None, **changes):
    value = request(nodes, **changes)
    return MODULE.evaluate(**{key: item for key, item in value.items() if key in PARAMETERS})


class ReplayTests(unittest.TestCase):
    def test_zero_llm_success_and_empty_history(self):
        result = evaluate()
        self.assertEqual(result["llm_calls"], 0)
        self.assertEqual(result["recommended"]["node_id"], "good")
        self.assertEqual(result["paths"][0]["path"], ["good"])
        self.assertTrue(result["historical_boundary"])
        empty = evaluate([])
        self.assertIsNone(empty["recommended"])
        self.assertEqual(empty["paths"], [])

    def test_current_project_and_environment_are_required(self):
        for field in ("project_id", "environment_scope"):
            for value in (None, "", " ", 1):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    evaluate(**{field: value})

    def test_scope_mismatch_cannot_be_disabled(self):
        for key, value in (("project_id", "project-b"), ("environment_scope", "production")):
            candidate = node(scope={**node()["scope"], key: value})
            with self.subTest(key=key):
                result = evaluate([candidate], strategy={"require_same_scope": False})
                self.assertEqual(result["candidates"], [])
                self.assertIsNone(result["recommended"])

    def test_recorded_runtime_and_dependencies_need_current_context(self):
        cases = [
            (node(scope={**node()["scope"], "runtime_id": "runtime-a"}), {}),
            (node(scope={**node()["scope"], "runtime_id": "runtime-a"}), {"runtime_id": "runtime-b"}),
            (node(dependencies=["lib@1"]), {}),
            (node(dependencies=["lib@1"]), {"dependencies": []}),
            (node(dependencies=["lib@1"]), {"dependencies": ["lib@2"]}),
        ]
        for candidate, context in cases:
            with self.subTest(context=context, node=candidate):
                self.assertIsNone(evaluate([candidate], **context)["recommended"])
        matching = node(scope={**node()["scope"], "runtime_id": "runtime-a"}, dependencies=["lib@1"])
        self.assertIsNotNone(evaluate([matching], runtime_id="runtime-a", dependencies=["lib@1"])["recommended"])

    def test_inactive_expired_or_unsubstantiated_history_is_not_recommended(self):
        candidates = [
            node("old", status="superseded"),
            node("retired", status="retired"),
            node("expired", scope={**node()["scope"], "valid_until": "2000-01-01T00:00:00Z"}),
            node("unsupported", evidence_refs=[]),
            node("constraint-gap", constraints=[]),
        ]
        result = evaluate(candidates)
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["recommended"])

    def test_current_constraints_and_dependencies_are_arrays_not_strings(self):
        for field in ("constraints", "dependencies"):
            for value in ("ab", {"a": 1}, ("a",), 3, [""], [1], ["a", "a"]):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    evaluate(**{field: value})

    def test_constraints_match_the_complete_recorded_set(self):
        historical = node(constraints=["preserve user data", "requires offline maintenance"])
        for current in ([], ["preserve user data"], ["preserve user data", "different condition"]):
            with self.subTest(current=current):
                result = evaluate([historical], constraints=current)
                self.assertEqual(result["candidates"], [])
                self.assertIsNone(result["recommended"])
        matching = evaluate([historical], constraints=["requires offline maintenance", "preserve user data"])
        self.assertEqual(matching["recommended"]["node_id"], "good")

    def test_result_guidance_preserves_low_authority_in_all_outcomes(self):
        cases = [
            ([node()], "CANDIDATES_FOUND", "VERIFY_CANDIDATE"),
            ([], "NO_APPLICABLE_EXPERIENCE", "REASON_OR_COLLECT_EVIDENCE"),
            ([node(result="failure")], "CANDIDATES_FOUND", "REASON_OR_COLLECT_EVIDENCE"),
            ([node(result="unknown")], "CANDIDATES_FOUND", "REASON_OR_COLLECT_EVIDENCE"),
        ]
        for history, status, next_action in cases:
            with self.subTest(status=status, next_action=next_action):
                result = evaluate(history)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["next_action"], next_action)
                self.assertEqual(result["recommendation_kind"], "historical_candidate")
                self.assertIs(result["execution_authorized"], False)
                self.assertIs(result["current_truth_established"], False)

    def test_numeric_types_finite_values_and_ranges_are_checked(self):
        for value in (True, "0.5", math.nan, math.inf, -math.inf, -0.1, 1.1, None):
            with self.subTest(progress=value), self.assertRaises(ValueError):
                evaluate([node(goal_progress=value)])
        for value in (True, "2", 0.5, -1, math.nan, math.inf, 10 ** 12 + 1, 10 ** 400):
            with self.subTest(cost=value), self.assertRaises(ValueError):
                evaluate([node(execution_cost={"llm_calls": value})])
        for field in ("cost_weight", "risk_weight", "early_stop_goal_progress"):
            for value in (False, "0.1", math.nan, math.inf, -0.1, 1.1):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    evaluate(strategy={field: value})

    def test_strategy_unknown_fields_types_and_depth_are_checked(self):
        cases = [{"max_depth": n} for n in (0, 33, True, 1.5, "4")]
        cases += [{"branch_priority": []}, {"branch_priority": "other"}, {"require_same_scope": "yes"}, {"avoid_failure_classes": "bad"}, {"surprise": True}]
        for strategy in cases:
            with self.subTest(strategy=strategy), self.assertRaises(ValueError):
                evaluate(strategy=strategy)

    def test_nested_unknown_fields_and_invalid_values_are_rejected(self):
        cases = [
            node(surprise=True),
            node(goal={**node()["goal"], "surprise": True}),
            node(scope={**node()["scope"], "surprise": True}),
            node(execution_cost={"surprise": 2}),
            node(result=[]), node(status=[]), node(risk=[]),
            node(failure_class=[]), node(timestamp="not-a-time"),
            node(scope={**node()["scope"], "valid_until": "2030-01-01"}),
            node(evidence_refs="not-an-array"), node(evidence_refs=["same", "same"]),
            node(state_summary=[]), node(hypothesis_refs=[3]),
        ]
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                evaluate([candidate])

    def test_graph_rejects_duplicate_dangling_and_cyclic_nodes(self):
        graphs = [
            [node("same"), node("same", action="different action")],
            [node(parent_id="missing")],
            [node(parent_id="good")],
            [node("a", parent_id="b"), node("b", parent_id="a")],
        ]
        for graph in graphs:
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                evaluate(graph)

    def test_filtered_parent_cannot_promote_descendant_to_candidate(self):
        parents = [
            node("parent", status="superseded"),
            node("parent", evidence_refs=[]),
            node("parent", scope={"project_id": "other", "environment_scope": "candidate"}),
            node("parent", constraints=[]),
            node("parent", goal={"why": "other", "what": "other"}),
        ]
        for parent in parents:
            with self.subTest(parent=parent):
                result = evaluate([parent, node("child", parent_id="parent")])
                self.assertEqual(result["candidates"], [])
                self.assertEqual(result["paths"], [])
                self.assertIsNone(result["recommended"])

    def test_avoided_failure_classes_prune_branches(self):
        result = evaluate([
            node("bad", failure_class="permission-risk"),
            node("child", parent_id="bad"),
            node("safe", goal_progress=0.4),
        ], strategy={"avoid_failure_classes": ["permission-risk"]})
        self.assertEqual([item["node_id"] for item in result["candidates"]], ["safe"])
        self.assertEqual(result["recommended"]["node_id"], "safe")

    def test_only_failures_or_unknown_results_do_not_recommend_action(self):
        result = evaluate([node("failed", result="failure"), node("unknown", result="unknown")])
        self.assertIsNone(result["recommended"])

    def test_ranking_strategies_survive_path_generation(self):
        expensive = node("expensive", goal_progress=1.0, execution_cost={"llm_calls": 8}, evidence_refs=["a", "b", "c"])
        cheap = node("cheap", goal_progress=0.6, execution_cost={"tool_calls": 0}, evidence_refs=["a"])
        expected = {"goal_progress": "expensive", "low_cost": "cheap", "evidence_first": "expensive", "balanced": "expensive"}
        for strategy, best in expected.items():
            with self.subTest(strategy=strategy):
                result = evaluate([expensive, cheap], strategy={"branch_priority": strategy, "cost_weight": 0, "risk_weight": 0})
                self.assertEqual(result["recommended"]["node_id"], best)
                self.assertEqual(result["paths"][0]["path"], [best])

    def test_path_uses_terminal_progress_and_accumulates_cost(self):
        result = evaluate([
            node("a", result="partial", goal_progress=0.9, execution_cost={"llm_calls": 1}),
            node("b", parent_id="a", result="failure", goal_progress=0.1, execution_cost={"llm_calls": 2}),
        ])
        path = result["paths"][0]
        self.assertEqual(path["path"], ["a", "b"])
        self.assertEqual(path["goal_progress"], 0.1)
        self.assertEqual(path["cost_proxy"], 3.0)

    def test_depth_limit_keeps_an_explicit_truncated_path(self):
        result = evaluate([
            node("a", result="partial"),
            node("b", parent_id="a", result="partial"),
            node("c", parent_id="b"),
        ], strategy={"max_depth": 2})
        path = result["paths"][0]
        self.assertEqual(path["path"], ["a", "b"])
        self.assertTrue(path["depth_truncated"])
        self.assertFalse(path["early_stopped"])

    def test_early_stop_preserves_observed_success(self):
        result = evaluate([node("a", goal_progress=0.9), node("b", parent_id="a", result="failure")])
        self.assertEqual(result["paths"][0]["path"], ["a"])
        self.assertTrue(result["paths"][0]["early_stopped"])

    def test_input_budget_bounds_iterators_without_exhausting_them(self):
        consumed = []

        def many():
            for i in range(1002):
                consumed.append(i)
                if i == 1001:
                    raise AssertionError("input iterator exceeded the 1001-item lookahead")
                yield node(str(i))

        with self.assertRaises(ValueError):
            evaluate(many())
        self.assertEqual(len(consumed), 1001)

    def test_api_size_budget_and_cost_overflow_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([node(action="x" * (2 * 1024 * 1024))])
        huge = 10 ** 308
        with self.assertRaises(ValueError):
            evaluate([node(execution_cost={"llm_calls": huge}), node("other", execution_cost={"llm_calls": huge})])

    def test_input_shape_limits_cover_metadata_and_reference_arrays(self):
        nested = {}
        for _ in range(33):
            nested = {"child": nested}
        malformed = [
            node(state_summary=nested),
            node(state_summary={"data": [None] * 100001}),
            node(evidence_refs=[str(i) for i in range(101)]),
            node(evidence_refs=["x" * 257]),
            node("x" * 257),
            node(action="x" * 4097),
        ]
        for candidate in malformed:
            with self.subTest(candidate_id=candidate["node_id"]), self.assertRaises(ValueError):
                evaluate([candidate])

    def test_long_valid_graph_is_iterative_and_truncates_at_budget(self):
        history = [node(str(i), parent_id=str(i - 1) if i else None, result="partial") for i in range(1000)]
        result = evaluate(history, strategy={"max_depth": 32})
        self.assertEqual(len(result["paths"][0]["path"]), 32)
        self.assertTrue(result["paths"][0]["depth_truncated"])
        self.assertEqual(len(result["candidates"]), 1000)

    def test_cli_success_and_rejections_are_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"

            def run(payload):
                path.write_text(payload, encoding="utf-8")
                return subprocess.run([sys.executable, str(ROOT / "replay" / "evaluator.py"), str(path)], capture_output=True, text=True, encoding="utf-8", timeout=10)

            good = run(json.dumps(request()))
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["recommended"]["node_id"], "good")
            cases = ["[]", "null", "{", json.dumps({**request(), "surprise": True}), json.dumps({key: value for key, value in request().items() if key != "experience_nodes"}), json.dumps({key: value for key, value in request().items() if key != "constraints"}), json.dumps(request(constraints=None)), json.dumps(request(dependencies=None)), json.dumps(request(strategy=None)), json.dumps(request()).replace('"goal_progress": 0.8', '"goal_progress": NaN'), '{"why":"a","why":"b"}', " " * (2 * 1024 * 1024 + 1)]
            for payload in cases:
                with self.subTest(payload=payload[:100]):
                    result = run(payload)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("Replay input rejected:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
            missing = subprocess.run([sys.executable, str(ROOT / "replay" / "evaluator.py"), str(path.with_name("missing.json"))], capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertNotEqual(missing.returncode, 0)
            self.assertNotIn("Traceback", missing.stderr)
            self.assertIn("Replay input rejected:", missing.stderr)


if __name__ == "__main__":
    unittest.main()
