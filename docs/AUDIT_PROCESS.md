# Iteration Audit Process

Use this process at every iteration (v1.1, v1.2, etc.) to score ZHC-Nova against the 4 reference links and publish a repeatable report.

## References

- ZeroClaw: https://github.com/openagen/zeroclaw
- OpenCode: https://github.com/anomalyco/opencode
- ZHC philosophy (Brian Roemmele): https://x.com/BrianRoemmele
- Agent Swarm: The One-Person Dev Team Setup: https://x.com/elvissun/status/2025920521871716562?s=20

## Audit Cadence

- Run once per iteration milestone and once before major deploy changes.
- Store every report in `docs/audits/` with date-based filenames.

## Rubric (12 metrics)

1. `swappable_modular` (8)
2. `secure_by_default` (15)
3. `lightweight_runtime` (8)
4. `provider_local_first` (9)
5. `multi_agent_swarm` (10)
6. `configurable_autonomy` (10)
7. `hybrid_memory_compression` (8)
8. `terminal_daemon_interfaces` (6)
9. `agentic_meta_engineering` (8)
10. `closed_loop_feedback` (7)
11. `cost_optimization` (6)
12. `ethical_auditable_governance` (5)

Scores are 0-10 per metric. Weighted total is 0-100.

## Commands

1) Create a scores file for this iteration:

```bash
cp docs/audits/SCORES_TEMPLATE.json docs/audits/2026-02-25-v1_1_scores.json
```

2) Fill numeric scores (0-10) in the copied file.

3) Generate report:

```bash
python3 scripts/audit_score.py \
  --scores docs/audits/2026-02-25-v1_1_scores.json \
  --output docs/audits/2026-02-25-v1_1_report.md \
  --iteration 2026-02-25-v1.1 \
  --notes "Post-implementation audit"
```

4) Generate closed-loop metrics report (before or alongside scoring):

```bash
python3 scripts/metrics_report.py \
  --days 7 \
  --iteration 2026-02-25-v1.1 \
  --output-json docs/audits/metrics/2026-02-25-v1_1_metrics.json \
  --output-md docs/audits/metrics/2026-02-25-v1_1_metrics.md
```

Shortcut command for quick reruns:

```bash
make audit
make metrics
```

## Report Requirements

Each generated report must include:

- Weighted score table
- Overall band (90+, 75-89, 60-74, <60)
- Top 3 lowest-scoring metrics
- Evidence notes with file references for each weak metric
- Action list for next iteration

## Iteration Gate Policy

- <60: block autonomy expansion; focus on security and runtime basics.
- 60-74: allow supervised execution only.
- 75-89: allow broader autonomous execution with gates.
- 90+: eligible for full zero-human flows where policy permits.
