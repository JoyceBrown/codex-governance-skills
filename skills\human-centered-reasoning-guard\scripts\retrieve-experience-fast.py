#!/usr/bin/env python3
"""Fast, read-only retrieval for the append-only experience store."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {
    "id", "status", "trigger", "action", "scope", "project_id", "source",
    "evidence", "confidence", "counterexamples", "supersedes", "created_at",
    "review_at",
}
VALID_STATUS = {"candidate", "active", "superseded", "expired"}
VALID_SCOPE = {"project", "global"}
MAX_LINE_BYTES = 16384


def searchable_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = [part for part in re.split(r"[\s,.;:!?/\\|()\[\]{}\"'`]+", lowered) if len(part) >= 2]
    for match in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        terms.append(match)
        terms.extend(match[index:index + 2] for index in range(len(match) - 1))
    return list(dict.fromkeys(term for term in terms if len(term) >= 2))


def parse_review(value: object, line_number: int) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid review_at at record {line_number}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_store(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if len(line.rstrip("\r\n").encode("utf-8")) > MAX_LINE_BYTES:
                raise ValueError(f"Record exceeds {MAX_LINE_BYTES} bytes")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Memory store contains invalid JSON at record {line_number}") from exc
            if not isinstance(record, dict) or not REQUIRED.issubset(record):
                raise ValueError(f"Memory store record {line_number} is missing a required field")
            if record["status"] not in VALID_STATUS:
                raise ValueError(f"Invalid status at record {line_number}")
            if record["scope"] not in VALID_SCOPE:
                raise ValueError(f"Invalid scope at record {line_number}")
            if record["scope"] == "project" and not str(record.get("project_id", "")).strip():
                raise ValueError(f"Project-scoped record lacks project_id at record {line_number}")
            if not str(record.get("trigger", "")).strip() or not str(record.get("action", "")).strip():
                raise ValueError(f"Empty trigger or action at record {line_number}")
            if not [item for item in record.get("evidence", []) if str(item).strip()]:
                raise ValueError(f"Empty evidence at record {line_number}")
            try:
                confidence = float(record["confidence"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid confidence at record {line_number}") from exc
            if not 0 <= confidence <= 1:
                raise ValueError(f"Confidence must be between 0 and 1 at record {line_number}")
            parse_review(record["review_at"], line_number)
            latest[str(record["id"])] = record
    if not latest:
        raise ValueError("Memory store is empty")
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--store-path", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--include-candidates", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        raise ValueError("Limit must be between 1 and 20")
    terms = searchable_terms(args.query)
    if not terms:
        raise ValueError("Query must contain at least one searchable term")

    now = datetime.now(timezone.utc)
    matches = []
    for record in read_store(Path(args.store_path)).values():
        if record["status"] in {"expired", "superseded"}:
            continue
        if not args.include_candidates and record["status"] != "active":
            continue
        if record["scope"] == "project" and record.get("project_id") != args.project_id:
            continue
        if parse_review(record["review_at"], 0) < now:
            continue
        text = (f"{record['trigger']} {record['action']} " + " ".join(map(str, record["evidence"]))).lower()
        hits = sum(1 for term in terms if term in text)
        if hits == 0:
            continue
        score = hits * 10 + float(record["confidence"]) * 5 + (2 if record["status"] == "active" else 0)
        matches.append((score, record))
    matches.sort(key=lambda item: item[0], reverse=True)
    for score, record in matches[:args.limit]:
        print(json.dumps({"score": score, "record": record}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
