import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ExecutionReliabilityScriptTests(unittest.TestCase):
    def run_script(self, name, *args, input_text=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_preflight_is_bounded_and_detects_unknown_root_for_high_risk(self):
        result = self.run_script("preflight.py", "--root", "relative-root", "--kind", "publish")
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertLessEqual(payload["budget"]["checks"], 8)

    def test_verify_artifact_rejects_name_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="execution-reliability-test-") as directory:
            artifact = Path(directory) / "actual.exe"
            artifact.write_bytes(b"artifact")
            result = self.run_script("verify-artifact.py", "--path", str(artifact), "--name", "Candidate.exe")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "BLOCKED")

    def test_retry_guard_stops_unknown_state_and_allows_one_low_risk_retry(self):
        unknown = self.run_script("retry-guard.py", "--attempt", "1", "--last-result", "unknown", "--same-target")
        self.assertNotEqual(unknown.returncode, 0)
        self.assertEqual(json.loads(unknown.stdout)["retry"], "ask")

        retry = self.run_script(
            "retry-guard.py", "--attempt", "1", "--last-result", "failed", "--same-target", "--transient"
        )
        self.assertEqual(retry.returncode, 0)
        self.assertEqual(json.loads(retry.stdout)["retry"], "allowed-once")

        second = self.run_script(
            "retry-guard.py", "--attempt", "2", "--last-result", "failed", "--same-target", "--transient"
        )
        self.assertNotEqual(second.returncode, 0)

    def test_receipt_is_redacted_allowlisted_and_bounded(self):
        receipt = {
            "request_id": "task-1",
            "status": "READY",
            "risk": "low",
            "scope": "build",
            "target": "artifact",
            "next_action": "verify",
            "command": "should be removed",
            "message": "token=secret-value",
        }
        result = self.run_script("write-receipt.py", input_text=json.dumps(receipt))
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertNotIn("command", payload)
        self.assertNotIn("secret-value", result.stdout)
        self.assertEqual(payload["schema"], "execution-reliability-receipt-v1")

    def test_receipt_cannot_write_governance_ledger_paths(self):
        receipt = {
            "request_id": "task-1",
            "status": "READY",
            "risk": "low",
            "scope": "build",
            "target": "artifact",
            "next_action": "verify",
        }
        with tempfile.TemporaryDirectory(prefix="execution-reliability-test-") as directory:
            destination = Path(directory) / ".agent-context" / "receipt.json"
            result = self.run_script(
                "write-receipt.py", "--out", str(destination), input_text=json.dumps(receipt)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
