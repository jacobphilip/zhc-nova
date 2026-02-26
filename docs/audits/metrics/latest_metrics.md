# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-26T13:51:38.860606+00:00
- Window: 2026-02-19T13:51:38.833408+00:00 -> 2026-02-26T13:51:38.833408+00:00

## KPI Summary

- Tasks: 181 (status: {'succeeded': 146, 'blocked': 20, 'running': 6, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.04m p90=0.08m
- Review gate: pass_rate=0.8272 pass=67 fail=1 missing=13 schema_complete_rate=0.8025 fail_then_pass=5
- Telemetry: avg_dispatch_ms=15231.81 total_cost_usd=0.077854 total_tokens=27977
- Telegram: success_rate=0.8807 error_rate=0.0222 command_success_rate=0.976 prodlike_command_success_rate=1.0 production_command_success_rate=0.9307 production_trace_command_success_rate=0.9388 unauthorized=0 poll_errors=11 timeouts=4 synthetic_rows=568
- Recovery: rate=0.1667 mttr_minutes=4.11 p90_recovery_minutes=7.14 incidents=12 recent_24h_rate=0.1667 instrumented_rate=1.0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Stabilize Telegram polling loop and restart behavior to reduce poll errors.

