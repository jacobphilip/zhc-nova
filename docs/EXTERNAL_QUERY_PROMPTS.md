# External Query Prompts (Grok Super + ChatGPT)

Use these as copy/paste prompts for Jacob external-brain queries.

## Prompt for Grok Super

```text
=== EXTERNAL QUERY NEEDED ===
TARGET: Grok
QUERY:
You are advising on ZHC-Nova direction. Use the context below plus the original Twitter post/profile that inspired this project.

ORIGIN CONTEXT (IMPORTANT):
- Twitter post URL: <PASTE_ORIGINAL_POST_URL>
- Twitter profile URL: <PASTE_ORIGINAL_PROFILE_URL>
- We want to stay aligned with that vision (agent swarm, one-person dev team, practical autonomy).

CURRENT PROJECT STATUS (Feb 2026):
- Ubuntu-first runtime is working with Telegram control plane + task router + approval/review gates.
- Real OpenCode execution is working in single-node mode.
- ZeroClaw gateway is running locally and healthy (`paired=true`).
- OAuth/provider path is set to `openai-codex` with `gpt-5-codex`.
- User-level systemd services are active for gateway + telegram control.
- Heavy-task flow is validated: plan -> review -> approve -> resume -> succeed.
- We fixed Telegram reliability issue by making `/approve` record-only (no dispatch) and `/resume` handle execution with longer timeout.
- Audit score currently ~76.32/100; recent metrics show stronger task throughput but still some telegram timeout/poll-error drag.

WHAT I WANT FROM YOU:
1) A brutally honest gap analysis vs the original Twitter vision.
2) The top 5 strategic priorities for the next 2 weeks.
3) A concrete 30/60/90 day roadmap for reaching “production-grade one-person agent company OS.”
4) What to cut/de-scope now to avoid over-engineering.
5) A KPI set (5-8 metrics) with target thresholds that indicate real readiness.
6) Biggest risks (technical + operational + governance) and mitigations.
7) A recommended “next milestone definition” I can execute this week.

Please be opinionated and specific.
CONTEXT (current task & why we need this):
• We have baseline runtime working and need sharper strategic focus.
• We want to align execution with original vision from the source Twitter post/profile.
=== END QUERY ===
```

## Prompt for ChatGPT

```text
=== EXTERNAL QUERY NEEDED ===
TARGET: GPT
QUERY:
Act as principal architect + operator coach for ZHC-Nova. Use the context below and the original Twitter inspiration to propose the best next steps.

ORIGIN CONTEXT (IMPORTANT):
- Twitter post URL: <PASTE_ORIGINAL_POST_URL>
- Twitter profile URL: <PASTE_ORIGINAL_PROFILE_URL>

CURRENT STATE SNAPSHOT:
- Ubuntu-first agent runtime operational.
- Telegram command center works with approval/review gates.
- Real heavy execution path works (OpenCode + Codex model).
- ZeroClaw gateway healthy and paired.
- Services running under user-level systemd.
- Heavy flow tested end-to-end and succeeding.
- Recent fixes: `/approve` now records approval only; `/resume` executes with extended timeout.
- Audit ~76.32/100; metrics improved but not yet “production hard.”

Please return a practical execution plan with these sections:
A) “Where we are” maturity assessment (architecture, reliability, operations, governance).
B) Priority backlog for next 10 working days (ordered, with acceptance criteria).
C) Reliability hardening checklist (service lifecycle, retries, idempotency, observability, incident response).
D) Productization checklist (operator UX, safety controls, docs/runbooks, deploy repeatability).
E) Recommended milestone gate to declare v1.2 ready.
F) What *not* to build yet.

Constrain recommendations to solo-founder execution speed and low operational overhead.
CONTEXT (current task & why we need this):
• We need a focused next-phase build plan from “working prototype” to “reliable operating system.”
• We want grounded decisions tied to the original vision source, not generic agent advice.
=== END QUERY ===
```
