# Contributing

Changes belong in the current collection repository. Keep each Skill usable on
its own, preserve its stated authority and lifecycle, and exchange only the
bounded `composition-v1` fields when composing Skills.

Before opening a change, run:

```powershell
.\scripts\validate-repository.ps1
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Do not add project ledgers, credentials, chat transcripts, Hook logs, or
runtime caches. A new side effect needs a documented owner, rollback path, and
regression coverage appropriate to its risk.
