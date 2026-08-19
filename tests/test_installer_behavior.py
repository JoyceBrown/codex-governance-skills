import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is required for installer behavior tests")
class InstallerBehaviorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
