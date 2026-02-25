# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-25T19:38:37.086205+00:00
- Window: 2026-02-18T19:38:37.077720+00:00 -> 2026-02-25T19:38:37.077720+00:00

## KPI Summary

- Tasks: 51 (status: {'succeeded': 31, 'blocked': 11, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.04m p90=0.5m
- Review gate: pass_rate=0.75 pass=18 fail=1 missing=5 schema_complete_rate=0.6667 fail_then_pass=5
- Telemetry: avg_dispatch_ms=20842.41 total_cost_usd=0.07169 total_tokens=6054
- Telegram: success_rate=0.8532 error_rate=0.055 unauthorized=0 poll_errors=1 timeouts=3

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Improve planner/reviewer quality: increase gate pass rate above 80%.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Stabilize Telegram polling loop and restart behavior to reduce poll errors.

