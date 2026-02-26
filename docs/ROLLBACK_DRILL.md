# Rollback Drill (CP-009)

This drill validates that the previous commit can be checked in isolation and pass a baseline smoke run.

## Run

```bash
chmod +x scripts/rollback_drill.sh
./scripts/rollback_drill.sh
```

## Evidence

- Report: `storage/memory/rollback_drill_latest.json`
- Drill uses a temporary git worktree at `HEAD~1` and runs simulation smoke validation.

## Pass Criteria

- `rollback_validation_ok` is `true`
- `smoke_exit_code` is `0`
