# Audit Reports

This directory stores iteration-level audit artifacts.

## Files

- `SCORES_TEMPLATE.json`: fill per-metric 0-10 scores.
- `<iteration>_scores.json`: scored input for one iteration.
- `<iteration>_report.md`: generated weighted report.
- `latest_scores.json` and `latest_report.md`: optional rolling pointers.
- `metrics/`: closed-loop operational metrics snapshots.

## Repeatable Flow

```bash
cp docs/audits/SCORES_TEMPLATE.json docs/audits/2026-02-25-v1_1_scores.json
# edit scores file
python3 scripts/audit_score.py \
  --scores docs/audits/2026-02-25-v1_1_scores.json \
  --output docs/audits/2026-02-25-v1_1_report.md \
  --iteration 2026-02-25-v1.1
```

You can also keep `docs/audits/latest_scores.json` updated and run:

```bash
make audit
make metrics
```
