# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-25T18:44:08.866632+00:00
- Window: 2026-02-18T18:44:08.862092+00:00 -> 2026-02-25T18:44:08.862092+00:00

## KPI Summary

- Tasks: 43 (status: {'blocked': 10, 'succeeded': 24, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.1m p90=0.51m
- Review gate: pass_rate=0.6667 pass=12 fail=1 missing=5 schema_complete_rate=0.5556 fail_then_pass=4
- Telemetry: avg_dispatch_ms=6272.52 total_cost_usd=0.061489 total_tokens=4683
- Telegram: success_rate=0.8197 error_rate=0.0656 unauthorized=0 poll_errors=0 timeouts=1

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Improve planner/reviewer quality: increase gate pass rate above 80%.
- Enforce complete reviewer checklist schema on all heavy-task reviews.

