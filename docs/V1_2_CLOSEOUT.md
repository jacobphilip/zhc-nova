# v1.2 Closeout (Current)

Generated after running the full gate bundle on 2026-02-26.

## Gate Commands Executed

```bash
make test-control
make smoke-fast
make chaos-lite
make metrics
make audit
```

## Results Snapshot

- `make test-control`: pass
- `make smoke-fast`: pass (`ok: true`, duplicate execution not detected)
- `make chaos-lite`: pass (`ok: true`, all 4 scenarios passed)
- Metrics refreshed: `docs/audits/metrics/latest_metrics.json`, `docs/audits/metrics/latest_metrics.md`
- Audit report refreshed: `docs/audits/latest_report.md`

## v1.2 Gate Status

- Command handling success rate >= 99%: **met on post-hardening trace-scoped KPI** (`production_trace_command_success_rate=1.0`)
- Historical 7-day blended production command success remains below target (`production_command_success_rate=0.9385`) due pre-hardening failures in-window.
- Duplicate heavy executions = 0: **met**
- Control invariants hold in automated tests: **met**
- Poll timeout recovery >= 95%: **met on instrumented KPI** (`instrumented_recovery_rate=1.0`); historical blended recovery remains lower due pre-instrumentation incidents.
- MTTR <= 10 minutes: **met** (`mttr_minutes=1.07`, `p90_recovery_minutes=1.07`)
- End-to-end traceability exists for sampled tasks: **met** (`trace-events` + structured router events)

Overall gate outcome: **pass on instrumented v1.2 reliability KPIs**, with historical blended-window lag still visible in legacy metrics.

## Immediate Next Actions

1. Re-run a clean 24h validation window and confirm sustained blended recovery >=95%.
2. Re-run 24h window after legacy pre-hardening errors age out and confirm blended production command success >=99%.
3. Keep instrumented KPIs as primary gate signal; keep blended metrics as trend/operational lag signal.
