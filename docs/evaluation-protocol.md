# Evaluation Protocol

This protocol separates repository readiness from real user benefit. It is a
repeatable local check, not an external benchmark.

## Inputs

- the checked-out collection revision and Python/PowerShell versions;
- the Skill entrypoints, composition schema, registry, installer, and embedded
  regression fixtures;
- an explicit task or user path when evaluating behavior beyond static
  contracts.

## Checks

1. Run `python -m unittest discover -s tests -p "test_*.py" -v`.
2. Run `scripts/validate-repository.ps1`, which includes mature Skill tests,
   PAO regressions, HCR regressions, Skill validation, and a temporary install
   smoke.
3. Validate any composition envelope with
   `python scripts/validate-composition.py`.
4. For a real host, run the PAO `live_app_server_smoke.py` manually. A
   `capability_gap` means the host did not expose the required shared endpoint;
   it is not evidence that the simulated transport contract passed live.
5. For user benefit, repeat the original user path against the intended target
   and record the observed result, identity, artifact, and remaining unknowns.

## Pass criteria and limits

Local checks pass only when their exit codes are zero and their receipts are
valid. They prove repository contracts and bounded local behavior. They do not
prove a live Codex host exposes app-server capabilities, that a model follows a
written receipt, or that a user's product outcome improved. Report those as
separate `VERIFIED`, `PARTIAL`, or `UNKNOWN` evidence rather than converting a
local test into a user-path claim.
