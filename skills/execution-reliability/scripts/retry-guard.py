#!/usr/bin/env python3
"""Decide whether one bounded retry is safe; never executes the action."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded retry decision")
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--last-result", choices=("not-run", "failed", "unknown", "passed"), required=True)
    parser.add_argument("--same-target", action="store_true")
    parser.add_argument("--same-input", action="store_true")
    parser.add_argument("--transient", action="store_true", help="caller has evidence the failure is transient")
    parser.add_argument("--risk", choices=("low", "medium", "high", "critical"), default="low")
    args = parser.parse_args()

    status, retry, next_action = "STOP", "stopped", "inspect current state before another attempt"
    if args.last_result == "passed":
        next_action = "do not repeat a successful action"
    elif args.last_result == "unknown":
        status, retry, next_action = "ASK", "ask", "check result files, locks, processes, and artifacts"
    elif args.attempt == 0 and args.last_result == "not-run":
        status, retry, next_action = "ALLOW", "not-needed", "execute the initial action"
    elif args.attempt == 1 and args.last_result == "failed" and args.same_target and args.same_input is False and args.transient and args.risk in {"low", "medium"}:
        status, retry, next_action = "ALLOW", "allowed-once", "change the known transient condition, then retry once"
    elif args.attempt == 1 and args.last_result == "failed" and args.same_target and args.transient and args.risk == "low":
        status, retry, next_action = "ALLOW", "allowed-once", "retry once after confirming the target"
    result = {
        "schema": "execution-reliability-retry-v1",
        "status": status,
        "retry": retry,
        "attempt": args.attempt,
        "next_action": next_action,
        "reason": "one retry maximum; unknown state and high-risk repeat are stopped",
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if status == "ALLOW" else 2


if __name__ == "__main__":
    sys.exit(main())
