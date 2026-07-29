from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SEVERITY_WEIGHTS = {"medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationSummary:
    case_count: int
    passed_count: int
    severity_weighted_recall: float
    domain_recall: float
    false_complete_count: int


def evaluate_case(case: dict[str, Any], run: dict[str, Any]) -> EvaluationResult:
    """Evaluate a normalized forward-test record without guessing missing data."""
    failures: list[str] = []
    detected = set(run.get("detected", []))
    domains = set(run.get("domains", []))
    required = set(case["required_detections"])
    required_domains = set(case["required_domains"])

    missing = sorted(required - detected)
    missing_domains = sorted(required_domains - domains)
    if missing:
        failures.append(f"missing detections: {', '.join(missing)}")
    if missing_domains:
        failures.append(f"missing domains: {', '.join(missing_domains)}")

    completion = run.get("completion")
    if completion not in {"Complete", "Partial", "Blocked"}:
        failures.append("completion is missing or invalid")
    if case.get("forbid_complete_when_missing") and completion == "Complete":
        if missing or missing_domains:
            failures.append("false Complete with unresolved planted coverage")

    expected = case.get("expected_completion")
    if expected and completion != expected:
        failures.append(f"expected completion {expected}, got {completion}")
    if expected == "Partial" and completion == "Complete":
        failures.append("Complete is forbidden for the declared unresolved boundary")

    return EvaluationResult(not failures, tuple(failures))


def summarize_cases(
    cases: list[dict[str, Any]], runs_by_case: dict[str, dict[str, Any]]
) -> EvaluationSummary:
    weighted_required = 0
    weighted_detected = 0
    required_domains = 0
    detected_domains = 0
    passed = 0
    false_complete = 0

    for case in cases:
        run = runs_by_case.get(case["case_id"], {})
        detected = set(run.get("detected", []))
        domains = set(run.get("domains", []))
        weight = SEVERITY_WEIGHTS[case["severity"]]
        required = set(case["required_detections"])
        case_domains = set(case["required_domains"])

        weighted_required += weight * len(required)
        weighted_detected += weight * len(required & detected)
        required_domains += len(case_domains)
        detected_domains += len(case_domains & domains)

        result = evaluate_case(case, run)
        passed += int(result.passed)
        false_complete += int(
            run.get("completion") == "Complete"
            and bool((required - detected) or (case_domains - domains))
        )

    return EvaluationSummary(
        case_count=len(cases),
        passed_count=passed,
        severity_weighted_recall=(
            weighted_detected / weighted_required if weighted_required else 1.0
        ),
        domain_recall=(detected_domains / required_domains if required_domains else 1.0),
        false_complete_count=false_complete,
    )
