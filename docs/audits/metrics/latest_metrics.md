# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-25T16:32:22.734395+00:00
- Window: 2026-02-18T16:32:22.732072+00:00 -> 2026-02-25T16:32:22.732072+00:00

## KPI Summary

- Tasks: 29 (status: {'succeeded': 14, 'failed': 6, 'blocked': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.01m p90=0.14m
- Review gate: pass_rate=0.5556 pass=5 fail=0 missing=4 schema_complete_rate=0.2222 fail_then_pass=1
- Telemetry: avg_dispatch_ms=7.46 total_cost_usd=0.040989 total_tokens=2353
- Telegram: success_rate=0 error_rate=0 unauthorized=0 poll_errors=0 timeouts=0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Improve planner/reviewer quality: increase gate pass rate above 80%.
- Enforce complete reviewer checklist schema on all heavy-task reviews.

