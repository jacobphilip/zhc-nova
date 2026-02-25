# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-25T16:24:49.284213+00:00
- Window: 2026-02-18T16:24:49.280830+00:00 -> 2026-02-25T16:24:49.280830+00:00

## KPI Summary

- Tasks: 22 (status: {'failed': 6, 'succeeded': 7, 'blocked': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.01m p90=0.14m
- Review gate: pass_rate=0.5556 pass=5 fail=0 missing=4 schema_complete_rate=0.2222 fail_then_pass=1
- Telemetry: avg_dispatch_ms=15.0 total_cost_usd=0.040989 total_tokens=1086
- Telegram: success_rate=0 error_rate=0 unauthorized=0 poll_errors=0 timeouts=0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Improve planner/reviewer quality: increase gate pass rate above 80%.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Enable OpenRouter pricing enrichment to improve cost signal quality.

