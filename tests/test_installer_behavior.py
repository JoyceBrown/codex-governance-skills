import json
import shutil
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is required for installer behavior tests")
class InstallerBehaviorTests(unittest.TestCase):
    def test_guard_install_preserves_gates_and_runs_replay(self):
        with tempfile.TemporaryDirectory(prefix="codex-guard-install-") as temporary:
            target = Path(temporary) / "skills"
            command = (
                f"& {self.ps_quote(INSTALLER)} "
                f"-TargetSkillsRoot {self.ps_quote(target)} "
                "-Names @('human-centered-reasoning-guard')"
            )
            result = self.run_powershell(command)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            guard = target / "human-centered-reasoning-guard"
            source = ROOT / "skills" / "human-centered-reasoning-guard"
            self.assertEqual(len(list(target.rglob("SKILL.md"))), 1)
            for relative in (
                "scripts/fact-gate.ps1", "scripts/goal-integrity-gate.ps1",
                "scripts/validate-target-identity.ps1", "scripts/sync-durable-ledger.ps1",
                "references/active-user-reconstruction.md",
            ):
                self.assertEqual((guard / relative).read_bytes(), (source / relative).read_bytes())
            replay = subprocess.run(
                [sys.executable, "-X", "utf8", str(guard / "replay/evaluator.py"),
                 str(guard / "examples/replay_request.json")],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            output = json.loads(replay.stdout)
            self.assertEqual(output["llm_calls"], 0)
            self.assertEqual(output["recommended"]["node_id"], "E2")
            validation = subprocess.run(
                [sys.executable, "-X", "utf8", str(guard / "validate_package.py")],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertFalse(json.loads(validation.stdout)["current_user_outcome_verified"])

    @staticmethod
    def ps_quote(value: Path) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def run_powershell(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_destination_conflict_is_preflighted_before_any_install(self):
        with tempfile.TemporaryDirectory(prefix="codex-installer-test-") as temporary:
            target = Path(temporary) / "skills"
            existing = target / "durable-context"
            existing.mkdir(parents=True)
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("existing", encoding="utf-8")

            command = (
                f"& {self.ps_quote(INSTALLER)} "
                f"-TargetSkillsRoot {self.ps_quote(target)} "
                "-Names @('intent-alignment','durable-context')"
            )
            result = self.run_powershell(command)

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "intent-alignment").exists())
            self.assertTrue(sentinel.exists())

    def test_commit_failure_rolls_back_the_whole_bundle(self):
        with tempfile.TemporaryDirectory(prefix="codex-installer-test-") as temporary:
            target = Path(temporary) / "skills"
            command = f"""
$script:moveCalls = 0
function Move-Item {{
    param([string]$LiteralPath, [string]$Destination)
    if (-not (Get-Variable -Scope Script -Name moveCalls -ErrorAction SilentlyContinue)) {{ $script:moveCalls = 0 }}
    $script:moveCalls++
    if ($script:moveCalls -eq 2) {{ throw 'injected commit failure' }}
    Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}}
& {self.ps_quote(INSTALLER)} -TargetSkillsRoot {self.ps_quote(target)} -Names @('intent-alignment','diagnose')
"""
            result = self.run_powershell(command)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("injected commit failure", result.stderr + result.stdout)
            self.assertFalse((target / "intent-alignment").exists())
            self.assertFalse((target / "diagnose").exists())
            self.assertEqual(list(target.glob(".install-*")), [])

    def test_force_backup_stays_outside_the_discoverable_skills_root(self):
        with tempfile.TemporaryDirectory(prefix="codex-installer-test-") as temporary:
            target = Path(temporary) / "skills"
            existing = target / "intent-alignment"
            existing.mkdir(parents=True)
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("existing", encoding="utf-8")

            command = (
                f"& {self.ps_quote(INSTALLER)} "
                f"-TargetSkillsRoot {self.ps_quote(target)} "
                "-Names @('intent-alignment') -Force"
            )
            result = self.run_powershell(command)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            receipt = json.loads(result.stdout)
            backup = Path(receipt["installed"][0]["backup"])
            self.assertNotIn(target, backup.parents)
            self.assertEqual(backup.parent.parent.parent.name, "skills-backups")
            self.assertEqual((backup / "sentinel.txt").read_text(encoding="utf-8"), "existing")
            self.assertTrue((target / "intent-alignment" / "SKILL.md").is_file())
            self.assertEqual(len(list(target.rglob("SKILL.md"))), 1)

    def test_force_commit_failure_restores_all_existing_skills(self):
        with tempfile.TemporaryDirectory(prefix="codex-installer-test-") as temporary:
            target = Path(temporary) / "skills"
            for name in ("intent-alignment", "diagnose"):
                existing = target / name
                existing.mkdir(parents=True)
                (existing / "sentinel.txt").write_text(name, encoding="utf-8")

            command = f"""
$script:moveCalls = 0
function Move-Item {{
    param([string]$LiteralPath, [string]$Destination)
    if (-not (Get-Variable -Scope Script -Name moveCalls -ErrorAction SilentlyContinue)) {{ $script:moveCalls = 0 }}
    $script:moveCalls++
    if ($script:moveCalls -eq 4) {{ throw 'injected force commit failure' }}
    Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}}
& {self.ps_quote(INSTALLER)} -TargetSkillsRoot {self.ps_quote(target)} -Names @('intent-alignment','diagnose') -Force
"""
            result = self.run_powershell(command)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("injected force commit failure", result.stderr + result.stdout)
            for name in ("intent-alignment", "diagnose"):
                existing = target / name
                self.assertEqual((existing / "sentinel.txt").read_text(encoding="utf-8"), name)
                self.assertFalse((existing / "SKILL.md").exists())
            self.assertEqual(list(target.glob(".install-*")), [])
            backup_root = Path(temporary) / "skills-backups" / "codex-governance-skills"
            self.assertEqual(list(backup_root.iterdir()) if backup_root.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
