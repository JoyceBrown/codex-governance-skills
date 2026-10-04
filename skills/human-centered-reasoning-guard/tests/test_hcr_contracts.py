"""Offline request/result/schema contracts, including boundary regressions."""

import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from replay.evaluator import evaluate
from replay.schema_validation import (
    MAX_REQUEST_BYTES, validate_schema_set, validate,
)


class HcrContractTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((ROOT / "examples" / "replay_request.json").read_text(encoding="utf-8"))

    def test_example_and_real_evaluator_output_match_offline_contract(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            validate_schema_set()
            validate(self.request, "hcr-replay-request.schema.json")
            result = evaluate(**self.request)
            validate(result, "hcr-replay-result.schema.json")
        self.assertEqual(result["recommended"]["node_id"], "E2")
        self.assertEqual(result["llm_calls"], 0)

    def test_scope_and_current_constraints_are_required(self):
        for field in ("project_id", "environment_scope", "constraints"):
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                del request[field]
                with self.assertRaises(ValueError):
                    validate(request, "hcr-replay-request.schema.json")

    def test_unknown_fields_nonfinite_values_and_budgets_are_rejected(self):
        variants = []
        unknown = copy.deepcopy(self.request)
        unknown["authorization"] = "pretend approved"
        variants.append(unknown)
        for value in (float("nan"), float("inf"), -0.1, 1.1, True, "0.5"):
            request = copy.deepcopy(self.request)
            request["experience_nodes"][0]["goal_progress"] = value
            variants.append(request)
        depth = copy.deepcopy(self.request)
        depth["strategy"]["max_depth"] = 33
        variants.append(depth)
        nodes = copy.deepcopy(self.request)
        nodes["experience_nodes"] *= 334
        variants.append(nodes)
        for index, request in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate(request, "hcr-replay-request.schema.json")

    def test_dependencies_unknown_is_not_an_arbitrary_json_value(self):
        for value in (None, "any", ["a", "a"], [""]):
            request = copy.deepcopy(self.request)
            request["dependencies"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(request, "hcr-replay-request.schema.json")

    def test_epistemic_and_external_governance_states_are_separate(self):
        record = {"claim": "A scoped observation", "epistemic_status": "OBSERVATION"}
        validate(record, "hcr-epistemic-record.schema.json")
        record["governance_status"] = "ACCEPTED_DECISION"
        record["governance_reference"] = "decision:123"
        validate(record, "hcr-epistemic-record.schema.json")
        del record["governance_reference"]
        with self.assertRaises(ValueError):
            validate(record, "hcr-epistemic-record.schema.json")
        for state in ("ACCEPTED_DECISION", "CANDIDATE", "SUPERSEDED"):
            with self.subTest(state=state), self.assertRaises(ValueError):
                validate({"claim": "claim", "epistemic_status": state}, "hcr-epistemic-record.schema.json")
        with self.assertRaises(ValueError):
            validate({"claim": "claim", "knowledge_status": "FACT"}, "hcr-epistemic-record.schema.json")

    def test_manual_telemetry_preserves_unknown_and_cannot_claim_verified(self):
        telemetry = {"telemetry_source": "manual", "telemetry_confidence": "unknown", "failure_count_total": None, "goal_progress": None}
        validate(telemetry, "hcr-telemetry.schema.json")
        for confidence in ("measured", "estimated", None):
            changed = dict(telemetry, telemetry_confidence=confidence)
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                validate(changed, "hcr-telemetry.schema.json")
        del telemetry["telemetry_confidence"]
        with self.assertRaises(ValueError):
            validate(telemetry, "hcr-telemetry.schema.json")
        validate({"telemetry_source": "unknown", "telemetry_confidence": "unknown"}, "hcr-telemetry.schema.json")

    def test_time_boundaries_require_timezone(self):
        for value in ("2026-09-18", "2026-09-18T12:00:00", "2026-13-99T12:00:00Z"):
            request = copy.deepcopy(self.request)
            request["experience_nodes"][0]["scope"]["valid_until"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(request, "hcr-replay-request.schema.json")

    def test_input_depth_and_byte_budgets_are_enforced(self):
        request = copy.deepcopy(self.request)
        request["why"] = "x" * MAX_REQUEST_BYTES
        with self.assertRaises(ValueError):
            validate(request, "hcr-replay-request.schema.json")
        nested = {}
        for _ in range(40):
            nested = {"child": nested}
        request = copy.deepcopy(self.request)
        request["experience_nodes"][0]["state_summary"] = nested
        with self.assertRaises(ValueError):
            validate(request, "hcr-replay-request.schema.json")

    def test_schema_loader_rejects_duplicate_keys_and_nonfinite_constants(self):
        samples = ('{"$id":"test","type":"string","type":"number"}', '{"$id":"test","minimum":NaN}')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hcr-test.schema.json"
            for value in samples:
                source.write_text(value, encoding="utf-8")
                with self.subTest(prefix=value[:40]), patch("replay.schema_validation.SCHEMA_ROOT", Path(directory)), self.assertRaises(ValueError):
                    validate_schema_set()

    def test_external_refs_and_unsupported_schema_keywords_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hcr-test.schema.json"
            for schema in ({"$ref": "https://untrusted.invalid/schema.json"}, {"$ref": "../outside.schema.json"}, {"type": "string", "unevaluatedProperties": False}, {"format": "hostname"}):
                source.write_text(json.dumps({"$id": "urn:hcr-test", **schema}), encoding="utf-8")
                with self.subTest(schema=schema), patch("replay.schema_validation.SCHEMA_ROOT", Path(directory)), patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
                    with self.assertRaises(ValueError):
                        validate({}, "hcr-test.schema.json")

    def test_internal_modules_cannot_take_gate_ownership(self):
        boundaries = (ROOT / "references" / "module-boundaries.md").read_text(encoding="utf-8")
        self.assertIn("gate-core", boundaries)
        self.assertIn("replay", boundaries)
        self.assertIn("Must not do", boundaries)
        self.assertIn("second ledger", boundaries)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Replay cannot grant permission", skill)
        self.assertIn("module-boundaries.md", skill)

    def test_standard_jsonschema_agrees_when_available_without_remote_resolution(self):
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("optional independent jsonschema validator is unavailable")
        schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "schemas").glob("*.schema.json")}

        def reject_remote(uri):
            raise AssertionError(f"network schema retrieval forbidden: {uri}")

        registry = Registry(retrieve=reject_remote).with_resources((name, Resource.from_contents(schema)) for name, schema in schemas.items())
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)
        for name, payload in (("hcr-replay-request.schema.json", self.request), ("hcr-replay-result.schema.json", evaluate(**self.request))):
            Draft202012Validator(schemas[name], registry=registry, format_checker=FormatChecker()).validate(payload)


if __name__ == "__main__":
    unittest.main()
