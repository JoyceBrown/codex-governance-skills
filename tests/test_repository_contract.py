import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {
    "bootstrap-codex-project",
    "durable-context",
    "human-centered-reasoning-guard",
    "deliberate-project",
    "intent-alignment",
    "diagnose",
    "tdd-loop",
    "architecture-health",
    "capability-director",
    "execution-reliability",
    "project-agent-orchestrator",
}
COLLECTION_REPOSITORY = "https://github.com/JoyceBrown/codex-governance-skills"
GOVERNANCE = {
    "bootstrap-codex-project",
    "durable-context",
    "human-centered-reasoning-guard",
    "deliberate-project",
    "project-agent-orchestrator",
}
LEGACY_IMPORTED = {
    "bootstrap-codex-project",
    "durable-context",
    "human-centered-reasoning-guard",
    "deliberate-project",
}
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".yaml", ".yml"}


class IntegratedRepositoryContractTests(unittest.TestCase):
    def test_exact_skill_set_and_entrypoints(self):
        actual = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual(actual, EXPECTED)
        for name in EXPECTED:
            skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(skill, r"(?m)^---\s*$")
            self.assertRegex(skill, rf"(?m)^name:\s*{re.escape(name)}\s*$")
            self.assertRegex(skill, r"(?m)^description:\s*.+$")

    def test_composition_contracts_are_present(self):
        for name in GOVERNANCE:
            skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Composition Contract", skill)
        composition = (ROOT / "docs" / "composition.md").read_text(encoding="utf-8")
        for field in (
            "schema_version",
            "request_id",
            "execution_status",
            "outcome_status",
            "evidence_refs",
            "next_action",
            "budget",
        ):
            self.assertIn(field, composition)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("composition-v1 Schema", readme)
        self.assertNotIn('"status": "FOUND | PARTIAL', readme)

    def test_capability_registry_is_complete_and_standalone(self):
        registry_path = ROOT / "docs" / "skill-capability-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["schema"],
            "codex-governance-skills-capability-registry-v1",
        )
        self.assertEqual(registry["composition_protocol"], "composition-v1")
        self.assertEqual(registry["envelope_schema"], "docs/composition.schema.json")
        self.assertEqual(registry["validator"], "scripts/validate-composition.py")
        records = {record["name"]: record for record in registry["skills"]}
        self.assertEqual(set(records), EXPECTED)
        required = {
            "name",
            "class",
            "route_role",
            "route_signals",
            "authority_owner",
            "authority_binding",
            "protocol_compatibility",
            "max_collaborators",
            "allowed_side_effects",
            "invocation",
            "required_dependencies",
            "optional_collaborators",
            "outputs",
            "write_scope",
            "forbidden_scope",
            "standalone_fallback",
        }
        for name, record in records.items():
            self.assertTrue(required.issubset(record), name)
            self.assertEqual(record["required_dependencies"], [], name)
            self.assertNotIn(name, record["optional_collaborators"], name)
            self.assertTrue(set(record["optional_collaborators"]).issubset(EXPECTED), name)
            self.assertTrue(record["standalone_fallback"].strip(), name)
            self.assertIn(record["route_role"], {"primary", "explicit_only"}, name)
            self.assertEqual(record["authority_binding"], "source_owner", name)
            self.assertIn("composition-v1", record["protocol_compatibility"], name)
            self.assertLessEqual(record["max_collaborators"], 2, name)
            self.assertIn("none", record["allowed_side_effects"], name)

    def test_every_entrypoint_declares_composition_and_standalone_behavior(self):
        for name in EXPECTED:
            skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("composition-v1", skill, name)
            self.assertRegex(skill, r"(?i)(standalone|独立运行|独立使用|回退)", name)
            for marker in ("evidence_refs", "next_action", "budget"):
                self.assertIn(marker, skill, name)

    def test_machine_readable_schema_is_bounded_and_matches_contract(self):
        schema = json.loads((ROOT / "docs" / "composition.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "codex-governance-skills/composition-v1")
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("parent_request_id", schema["required"])
        self.assertEqual(schema["properties"]["budget"]["properties"]["depth"]["maximum"], 2)
        self.assertIn("spent_chars", schema["properties"]["budget"]["properties"])
        self.assertIn("spent_calls", schema["properties"]["budget"]["properties"])
        self.assertEqual(schema["properties"]["evidence_refs"]["maxItems"], 20)

    def test_route_and_protocol_tools_are_published(self):
        registry = json.loads((ROOT / "docs" / "skill-capability-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["authority"], "docs/composition.md")
        self.assertTrue((ROOT / "scripts" / "route-composition.py").is_file())
        self.assertTrue((ROOT / "tests" / "test_route_composition.py").is_file())
        self.assertTrue((ROOT / "scripts" / "validate-artifacts.py").is_file())
        self.assertTrue((ROOT / "scripts" / "validate-release-metadata.py").is_file())
        self.assertTrue((ROOT / "schemas" / "artifact.schema.json").is_file())

    def test_published_examples_are_connected_to_repository_gate(self):
        gate = (ROOT / "scripts" / "validate-repository.ps1").read_text(encoding="utf-8")
        self.assertIn("validate-artifacts.py", gate)
        self.assertIn("validate-composition.py", gate)
        self.assertIn("ConvertFrom-Json", gate)
        self.assertNotIn("-like '*\\examples\\composition\\valid-envelope.json'", gate)
        examples = list((ROOT / "examples").rglob("*.json"))
        self.assertGreaterEqual(len(examples), 11)

    def test_architecture_decisions_and_scope_boundaries_are_published(self):
        for path in (
            ROOT / "docs" / "adr" / "0001-pao-execution-boundary.md",
            ROOT / "docs" / "adr" / "0002-composition-v1.md",
            ROOT / "docs" / "adr" / "0003-atomic-skills-stay-lightweight.md",
            ROOT / "docs" / "glossary.md",
            ROOT / "docs" / "out-of-scope" / "security-review.md",
            ROOT / "docs" / "out-of-scope" / "deep-planning-dialogue.md",
            ROOT / "CHANGELOG.md",
        ):
            self.assertTrue(path.is_file(), path)
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_pao_queue_contract_stays_within_the_single_plan(self):
        skill = (SKILLS / "project-agent-orchestrator" / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("Execution Queue Contract", "slice_id", "resume_cursor", "不创建替代队列"):
            self.assertIn(marker, skill)
        plans = (SKILLS / "bootstrap-codex-project" / "assets" / "templates" / "PLANS.md").read_text(encoding="utf-8")
        self.assertIn("## Execution queue (optional)", plans)
        self.assertIn("not a second plan", plans)
        checkpoint = (SKILLS / "bootstrap-codex-project" / "assets" / "templates" / "current-work.md").read_text(encoding="utf-8")
        for marker in ("last_completed_slice", "next_slice", "resume_cursor", "stop_reason"):
            self.assertIn(marker, checkpoint)

    def test_composition_protocol_separates_status_domains_and_lifecycle(self):
        composition = (ROOT / "docs" / "composition.md").read_text(encoding="utf-8")
        for marker in (
            "composition-v1",
            "recovery_status",
            "action_status",
            "review_status",
            "execution_status",
            "authority_owner",
            "degradation",
            "lifecycle",
            "组合深度默认不超过 2",
            "禁止回指祖先形成循环",
            "单技能合同",
            "组合负例",
        ):
            self.assertIn(marker, composition)
        self.assertIn("recovery-status.md", composition)

    def test_artifact_status_is_not_a_shared_domain_enum(self):
        schema = json.loads((ROOT / "schemas" / "artifact.schema.json").read_text(encoding="utf-8"))
        status = schema["allOf"][0]["then"]["properties"]["status"]
        self.assertEqual(status["type"], "string")
        self.assertNotIn("enum", status)
        artifact_validator = (ROOT / "scripts" / "validate-artifacts.py").read_text(encoding="utf-8")
        self.assertNotIn("RECEIPT_STATUSES", artifact_validator)

    def test_recovery_status_has_one_semantic_source(self):
        canonical = SKILLS / "durable-context" / "references" / "recovery-status.md"
        self.assertTrue(canonical.is_file())
        text = canonical.read_text(encoding="utf-8")
        for status in ("FOUND", "PARTIAL", "NOT_FOUND", "CONFLICTED", "BLOCKED_UNCERTAINTY"):
            self.assertIn(f"`{status}`", text)
        durable = (SKILLS / "durable-context" / "SKILL.md").read_text(encoding="utf-8")
        pao = (SKILLS / "project-agent-orchestrator" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("recovery-status.md", durable)
        self.assertIn("recovery-status.md", pao)
        self.assertIn("不另立语义", pao)

    def test_hcr_internal_boundaries_are_explicit(self):
        reference = SKILLS / "human-centered-reasoning-guard" / "references" / "module-boundaries.md"
        self.assertTrue(reference.is_file())
        text = reference.read_text(encoding="utf-8")
        for module in ("gate-core", "cognitive-mode", "replay", "experience-store", "ledger-bridge"):
            self.assertIn(f"`{module}`", text)
        self.assertIn("not separate", text)
        skill = (SKILLS / "human-centered-reasoning-guard" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("module-boundaries.md", skill)

    def test_license_and_notice_declare_scope(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("SPDX-License-Identifier: MIT", license_text)
        self.assertIn("Joyce Brown", license_text)
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("current collection", notice)
        self.assertIn("user-supplied reference", notice)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("MIT", readme)
        self.assertIn("NOTICE", readme)

    def test_ui_metadata_matches_skill_names(self):
        for name in EXPECTED:
            metadata = (SKILLS / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn("display_name:", metadata)
            self.assertIn("short_description:", metadata)

    def test_collection_is_the_only_maintenance_authority(self):
        manifest = json.loads(
            (ROOT / "docs" / "source-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["schema"], "codex-governance-skills-source-manifest-v3"
        )
        self.assertEqual(manifest["authority"]["repository"], COLLECTION_REPOSITORY)
        records = {record["skill"]: record for record in manifest["skills"]}
        legacy_records = {name: record for name, record in records.items() if "legacy_import" in record}
        self.assertEqual(set(legacy_records), LEGACY_IMPORTED)
        self.assertIn("execution-reliability", records)
        self.assertEqual(records["execution-reliability"].get("origin"), "collection-native")
        self.assertIn("project-agent-orchestrator", records)
        self.assertEqual(records["project-agent-orchestrator"].get("origin"), "collection-native")
        for name, record in legacy_records.items():
            self.assertEqual(record["authority_repository"], COLLECTION_REPOSITORY)
            self.assertEqual(record["source_path"], f"skills/{name}")
            self.assertRegex(record["legacy_import"]["commit"], r"^[0-9a-f]{40}$")
            archive_ref = record["legacy_import"]["archive_ref"]
            self.assertEqual(archive_ref, f"refs/tags/legacy/{name}/main")
            archived_commit = subprocess.run(
                ["git", "rev-parse", f"{archive_ref}^{{commit}}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(archived_commit, record["legacy_import"]["commit"])
            self.assertNotEqual(
                record["legacy_import"]["repository"], COLLECTION_REPOSITORY
            )

    def test_mature_skill_regressions_are_embedded(self):
        for name in ("bootstrap-codex-project", "durable-context", "deliberate-project"):
            tests = list((SKILLS / name / "tests").glob("test_*.py"))
            self.assertTrue(tests, name)
        self.assertTrue(
            (SKILLS / "durable-context" / "scripts" / "audit_skill_collection.py").is_file()
        )
        self.assertTrue(
            (
                SKILLS
                / "human-centered-reasoning-guard"
                / "scripts"
                / "run-regression-tests.ps1"
            ).is_file()
        )
        self.assertTrue(
            (
                SKILLS
                / "project-agent-orchestrator"
                / "scripts"
                / "test_host_adapter.py"
            ).is_file()
        )

    def test_human_guard_active_user_perspective_contract(self):
        skill = (SKILLS / "human-centered-reasoning-guard" / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            SKILLS
            / "human-centered-reasoning-guard"
            / "references"
            / "active-user-reconstruction.md"
        )
        self.assertTrue(reference.is_file())
        self.assertIn("Active User-Perspective Mode", skill)
        self.assertIn("Pause code edits", skill)
        self.assertIn("CONTINUE", skill)
        self.assertIn("intent-alignment", skill)
        protocol = reference.read_text(encoding="utf-8")
        for marker in ("Why now", "User job", "Observable success", "ASSUMPTION", "NO CHANGE REQUIRED", "Output Contract"):
            self.assertIn(marker, protocol)

    def test_git_paths_and_published_text_blobs_are_portable(self):
        paths = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        tracked = [path.decode("utf-8") for path in paths if path]
        self.assertTrue(tracked)
        for path in tracked:
            self.assertNotIn("\\", path)
            self.assertFalse(path.startswith("/"))
            if Path(path).suffix.lower() not in TEXT_SUFFIXES and Path(path).name not in {
                ".gitattributes",
                ".gitignore",
            }:
                continue
            blob = subprocess.run(
                ["git", "show", f":{path}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertFalse(blob.startswith(b"\xef\xbb\xbf"), path)
            self.assertNotIn(b"\r\n", blob, path)
            blob.decode("utf-8", errors="strict")

    def test_public_tree_excludes_private_runtime_material(self):
        forbidden_names = {".agent-context", "hook-events.jsonl", "conversation-history.md", ".runtime", ".git"}
        for path in ROOT.rglob("*"):
            lowered = {part.lower() for part in path.relative_to(ROOT).parts}
            if ".git" in lowered:
                continue
            self.assertTrue(forbidden_names.isdisjoint(lowered), str(path))
        content_files = [
            p for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".sqlite3"}
        ]
        forbidden_values = re.compile(r"(?:C:\\Users\\JIE|E:\\AI Project|gho_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{20,})", re.I)
        for path in content_files:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(forbidden_values.search(text), str(path))

    def test_capability_director_is_read_only_and_bounded(self):
        skill = (SKILLS / "capability-director" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("最多比较 3 个候选", skill)
        self.assertIn("不得自动下载代码", skill)
        self.assertIn("Capability Receipt", skill)

    def test_execution_reliability_is_bounded_and_non_governing(self):
        skill = (SKILLS / "execution-reliability" / "SKILL.md").read_text(encoding="utf-8")
        for marker in (
            "Composition Contract",
            "不写 `.agent-context`",
            "不自动调用“三堂会审”",
            "同一目标、同一状态、同一动作最多自动重试一次",
            "review_candidate",
        ):
            self.assertIn(marker, skill)
        self.assertIn("不注册全局 Hook", skill)
        self.assertTrue((SKILLS / "execution-reliability" / "scripts" / "preflight.py").is_file())
        self.assertTrue((SKILLS / "execution-reliability" / "scripts" / "verify-artifact.py").is_file())
        self.assertTrue((SKILLS / "execution-reliability" / "scripts" / "retry-guard.py").is_file())
        self.assertTrue((SKILLS / "execution-reliability" / "scripts" / "write-receipt.py").is_file())

    def test_execution_reliability_has_no_second_ledger_or_auto_adjudication(self):
        skill = (SKILLS / "execution-reliability" / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("SQLite", "常驻 Broker", "自动触发它"):
            self.assertNotIn(marker, skill)


if __name__ == "__main__":
    unittest.main()
