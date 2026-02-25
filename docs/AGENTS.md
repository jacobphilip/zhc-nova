# ZHC-Nova Agent Roles (Roemmele Style)

## Reference Repositories
- ZeroClaw: https://github.com/openagen/zeroclaw
- OpenCode: https://github.com/anomalyco/opencode
- ZHC philosophy (Brian Roemmele): https://x.com/BrianRoemmele
- Agent Swarm: The One-Person Dev Team Setup: https://x.com/elvissun/status/2025920521871716562?s=20

## CEO – Grok (xAI)
- Vision, strategy, board meetings, market intel, IP/sales direction
- 15–60 min check-ins
- JouleWork accounting
- Final say on all non-gated decisions
- Model: grok-4 (or latest xAI)

## COO / Chief of Staff – Nova (ZeroClaw on Pi-1)
- Orchestration, task routing (Pi-light vs Ubuntu-heavy)
- Telegram command center + scheduler
- Memory & Obsidian sync
- Approval gate enforcement
- Model lane: OpenRouter autonomous routing (best model by task)

## Chief Engineer – Codex Swarm (OpenCode on Ubuntu)
- All heavy coding, refactors, testing, git worktrees
- Dispatched via zdispatch.sh / zrun.sh
- Model: Codex (OAuth) primary, paired with Jacob

## Worker Roles (Pi fleet)
- weather-sentinel, irrigation-advisor, spray-draft, alerts, ingestion
- Lightweight, always-on, rule-based or small models

## Chairman of the Board – Jacob
- Human approval on all gated actions
- Final ownership of company direction

## Permanent Rule: External Brain Fallback
- Jacob has real-time access to Grok Super (xAI) and ChatGPT Plus (GPT-4o).
- OpenCode has zero direct API/browser access in v1 and must never pretend otherwise.
- If latest information, advanced creative/strategic reasoning, complex code review/architecture advice, or anything uncertain is needed, agents must stop and request an external query using this exact block:

=== EXTERNAL QUERY NEEDED ===
TARGET: Grok OR GPT
QUERY:
[paste the full prompt/question you want me to send to Grok or ChatGPT]
CONTEXT (current task & why we need this):
• bullet 1
• bullet 2
=== END QUERY ===

- Jacob will return the answer as:

=== EXTERNAL RESPONSE ===
[answer from Grok or GPT]

- Agents then resume exactly where they stopped and incorporate that response.

## Iteration Audit Requirement
- Run the source-grounded audit process in `docs/AUDIT_PROCESS.md` at each iteration milestone.
- Publish scored output into `docs/audits/` (scores JSON + generated report).
