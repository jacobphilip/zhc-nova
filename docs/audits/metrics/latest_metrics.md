# ZHC-Nova Metrics Report - latest

- Generated: 2026-02-25T15:56:20.585217+00:00
- Window: 2026-02-18T15:56:20.583836+00:00 -> 2026-02-25T15:56:20.583836+00:00

## KPI Summary

- Tasks: 19 (status: {'failed': 4, 'succeeded': 6, 'blocked': 8, 'cancelled': 1})
- Policy blocks: 3 ({'readonly_mode': 1, 'blocked_prompt_keyword': 1, 'unknown_task_type': 1})
- Approval latency: median=0.01m p90=0.14m
- Review gate: pass_rate=0.1429 pass=1 fail=0 missing=6
- Telemetry: avg_dispatch_ms=17.0 total_cost_usd=0.020452 total_tokens=451
- Telegram: success_rate=0 error_rate=0 unauthorized=0

## Top 5 Next Actions

- Tune execution policy allowlists/keywords to reduce unnecessary policy blocks.
- Improve planner/reviewer quality: increase gate pass rate above 80%.
- Enable OpenRouter pricing enrichment to improve cost signal quality.
- Improve context compaction effectiveness (target lower average compression ratio).

