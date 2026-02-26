# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-26T11:38:02.001087+00:00
- Window: 2026-02-19T11:38:01.982979+00:00 -> 2026-02-26T11:38:01.982979+00:00

## KPI Summary

- Tasks: 123 (status: {'succeeded': 90, 'blocked': 18, 'running': 6, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.04m p90=0.14m
- Review gate: pass_rate=0.8209 pass=55 fail=1 missing=11 schema_complete_rate=0.791 fail_then_pass=5
- Telemetry: avg_dispatch_ms=24600.85 total_cost_usd=0.07169 total_tokens=17495
- Telegram: success_rate=0.8361 error_rate=0.029 command_success_rate=0.9674 prodlike_command_success_rate=1.0 production_command_success_rate=0.9351 production_trace_command_success_rate=0.96 unauthorized=0 poll_errors=10 timeouts=4 synthetic_rows=354
- Recovery: rate=0.0909 mttr_minutes=1.07 p90_recovery_minutes=1.07 incidents=11 recent_24h_rate=0.0909 instrumented_rate=1.0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Stabilize Telegram polling loop and restart behavior to reduce poll errors.

