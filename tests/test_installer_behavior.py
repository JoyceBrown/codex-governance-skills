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
    def test_destination_conflict_is_preflighted_before_any_install(self):
        with tempfile.TemporaryDirectory(prefix="codex-installer-test-") as temporary:
            target = Path(temporary) / "skills"
            existing = target / "durable-context"
            existing.mkdir(parents=True)
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("existing", encoding="utf-8")

            def ps_quote(value: Path) -> str:
                return "'" + str(value).replace("'", "''") + "'"

            command = (
                f"& {ps_quote(INSTALLER)} "
                f"-TargetSkillsRoot {ps_quote(target)} "
                "-Names @('intent-alignment','durable-context')"
            )
            result = subprocess.run(
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
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "intent-alignment").exists())
            self.assertTrue(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
