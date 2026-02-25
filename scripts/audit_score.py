#!/usr/bin/env python3
"""Generate weighted ZHC-Nova architecture/process audit reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    weight: float


METRICS: tuple[Metric, ...] = (
    Metric("swappable_modular", "Swappable Modular", 8.0),
    Metric("secure_by_default", "Secure-by-Default", 15.0),
    Metric("lightweight_runtime", "Lightweight Runtime", 8.0),
    Metric("provider_local_first", "Provider-Agnostic/Local-First", 9.0),
    Metric("multi_agent_swarm", "Multi-Agent Swarm + Rivalry", 10.0),
    Metric("configurable_autonomy", "Configurable Autonomy", 10.0),
    Metric("hybrid_memory_compression", "Hybrid Memory + Compression", 8.0),
    Metric("terminal_daemon_interfaces", "Terminal/Daemon Interfaces", 6.0),
    Metric("agentic_meta_engineering", "Agentic Meta-Engineering", 8.0),
    Metric("closed_loop_feedback", "Closed-Loop Feedback", 7.0),
    Metric("cost_optimization", "Cost Optimization", 6.0),
    Metric("ethical_auditable_governance", "Ethical/Auditable Governance", 5.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weighted audit report")
    parser.add_argument("--scores", required=True, help="Path to scores JSON")
    parser.add_argument(
        "--output", required=True, help="Path to output markdown report"
    )
    parser.add_argument(
        "--iteration", required=True, help="Iteration label, e.g. 2026-02-25"
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional short note included in report header",
    )
    return parser.parse_args()


def load_scores(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Scores file must contain a JSON object")
    scores: dict[str, float] = {}
    for metric in METRICS:
        if metric.key not in payload:
            raise ValueError(f"Missing score for metric: {metric.key}")
        raw = payload[metric.key]
        if not isinstance(raw, (int, float)):
            raise ValueError(f"Score for {metric.key} must be numeric")
        if raw < 0 or raw > 10:
            raise ValueError(f"Score for {metric.key} must be between 0 and 10")
        scores[metric.key] = float(raw)
    return scores


def score_band(total: float) -> str:
    if total >= 90:
        return "Production-ready one-person AI company stack (Zero-Human ready)"
    if total >= 75:
        return "Strong foundation - fix security/autonomy gaps"
    if total >= 60:
        return "Viable but risky - major refactoring needed"
    return "Not yet an agentic stack (traditional dev with LLM wrapper)"


def render_report(iteration: str, notes: str, scores: dict[str, float]) -> str:
    lines: list[str] = []
    lines.append(f"# ZHC-Nova Audit Report - {iteration}")
    lines.append("")
    if notes:
        lines.append(f"Notes: {notes}")
        lines.append("")

    lines.append("## Weighted Scorecard")
    lines.append("")
    lines.append("| # | Metric | Weight | Score (0-10) | Weighted |")
    lines.append("|---|--------|--------|--------------|----------|")

    total = 0.0
    weighted_rows: list[tuple[float, str, float, float]] = []
    for idx, metric in enumerate(METRICS, start=1):
        score = scores[metric.key]
        weighted = (score / 10.0) * metric.weight
        total += weighted
        weighted_rows.append((weighted, metric.label, score, metric.weight))
        lines.append(
            f"| {idx} | {metric.label} | {metric.weight:.0f}% | {score:.1f} | {weighted:.2f} |"
        )

    lines.append(f"|   | **TOTAL** | **100%** | - | **{total:.2f}/100** |")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append(f"- Overall score: **{total:.2f}/100**")
    lines.append(f"- Band: **{score_band(total)}**")
    lines.append("")

    lines.append("## Lowest Metrics (Priority Fixes)")
    lines.append("")
    for weighted, label, score, weight in sorted(
        weighted_rows, key=lambda item: item[0]
    )[:3]:
        lines.append(
            f"- {label}: {score:.1f}/10 (weight {weight:.0f}%, contribution {weighted:.2f})"
        )
    lines.append("")
    lines.append("## Evidence Notes")
    lines.append("")
    lines.append(
        "- Add file-path evidence for each metric in this section each iteration."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    scores_path = Path(args.scores).resolve()
    output_path = Path(args.output).resolve()
    scores = load_scores(scores_path)
    report = render_report(args.iteration, args.notes, scores)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
