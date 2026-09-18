"""Validate the integrated Guard package and its real Replay example offline."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re

from replay.evaluator import evaluate
from replay.schema_validation import validate, validate_schema_set


ROOT = Path(__file__).resolve().parent


def validate_package() -> dict:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    parts = skill.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("SKILL.md must start with YAML frontmatter")
    if not re.search(r"(?m)^name:\s*human-centered-reasoning-guard\s*$", parts[1]):
        raise ValueError("The sole skill entrypoint must remain human-centered-reasoning-guard")
    if len(list(ROOT.rglob("SKILL.md"))) != 1:
        raise ValueError("The package must have one discoverable SKILL.md")
    for filename in (
        "scripts/fact-gate.ps1", "scripts/goal-integrity-gate.ps1",
        "scripts/validate-target-identity.ps1", "scripts/run-regression-tests.ps1",
        "references/active-user-reconstruction.md", "references/cognitive-reasoning.md",
        "references/host-spec-v1.md", "agents/openai.yaml",
    ):
        if not (ROOT / filename).is_file():
            raise ValueError(f"Missing Guard resource: {filename}")
    for path in ROOT.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    schemas = validate_schema_set()
    request = json.loads((ROOT / "examples/replay_request.json").read_text(encoding="utf-8"))
    validate(request, "hcr-replay-request.schema.json")
    result = evaluate(**request)
    validate(result, "hcr-replay-result.schema.json")
    if result["llm_calls"] != 0 or not result["recommended"] or result["recommended"]["node_id"] != "E2":
        raise ValueError("The bundled Replay example did not return the expected historical candidate")
    return {
        "status": "passed",
        "schema_count": len(schemas),
        "example_candidate": result["recommended"]["node_id"],
        "llm_calls": 0,
        "current_user_outcome_verified": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate_package(), ensure_ascii=False))
    except (OSError, SyntaxError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Package validation failed: {exc}") from exc
