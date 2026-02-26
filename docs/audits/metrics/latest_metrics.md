# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-26T15:33:44.634713+00:00
- Window: 2026-02-19T15:33:44.595578+00:00 -> 2026-02-26T15:33:44.595578+00:00

## KPI Summary

- Tasks: 219 (status: {'succeeded': 183, 'blocked': 21, 'running': 6, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.04m p90=0.08m
- Review gate: pass_rate=0.8315 pass=74 fail=1 missing=14 schema_complete_rate=0.809 fail_then_pass=5
- Telemetry: avg_dispatch_ms=12170.2 total_cost_usd=0.077854 total_tokens=34887
- Telegram: success_rate=0.8989 error_rate=0.0193 command_success_rate=0.9794 prodlike_command_success_rate=1.0 production_command_success_rate=0.9385 production_trace_command_success_rate=1.0 unauthorized=0 poll_errors=11 timeouts=4 synthetic_rows=763
- Recovery: rate=0.0833 mttr_minutes=1.07 p90_recovery_minutes=1.07 incidents=12 recent_24h_rate=0.0833 instrumented_rate=1.0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Stabilize Telegram polling loop and restart behavior to reduce poll errors.

