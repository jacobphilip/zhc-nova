# ZHC-Nova Project Agent Rules

This file defines project-local agent behavior for OpenCode sessions in this repository.

## Permanent Rule: External Brain Fallback

- Jacob has real-time access to Grok Super (xAI) and ChatGPT Plus (GPT-4o).
- OpenCode has zero direct API/browser access in v1 and must never pretend otherwise.
- If latest information, advanced creative/strategic reasoning, complex code review/architecture advice, or anything uncertain is needed, agents must stop and request external input using this exact block:

=== EXTERNAL QUERY NEEDED ===
TARGET: Grok OR GPT
QUERY:
[paste the full prompt/question you want me to send to Grok or ChatGPT]
CONTEXT (current task & why we need this):
• bullet 1
• bullet 2
=== END QUERY ===

- Jacob will reply with:

=== EXTERNAL RESPONSE ===
[answer from Grok or GPT]

- Resume exactly where execution paused and incorporate that response.

## Source of truth

- Role definitions and operating details: `docs/AGENTS.md`
- Runtime procedure and fallback operations: `docs/OPERATIONS.md`
