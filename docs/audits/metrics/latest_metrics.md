# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-26T03:50:04.148490+00:00
- Window: 2026-02-19T03:50:04.132845+00:00 -> 2026-02-26T03:50:04.132845+00:00

## KPI Summary

- Tasks: 101 (status: {'succeeded': 70, 'blocked': 17, 'running': 5, 'failed': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.04m p90=0.39m
- Review gate: pass_rate=0.8197 pass=50 fail=1 missing=10 schema_complete_rate=0.7869 fail_then_pass=5
- Telemetry: avg_dispatch_ms=31528.49 total_cost_usd=0.07169 total_tokens=13756
- Telegram: success_rate=0.8182 error_rate=0.0338 command_success_rate=0.9615 production_command_success_rate=0.9385 production_trace_command_success_rate=1.0 unauthorized=0 poll_errors=4 timeouts=4 synthetic_rows=275

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Enforce complete reviewer checklist schema on all heavy-task reviews.
- Stabilize Telegram polling loop and restart behavior to reduce poll errors.

