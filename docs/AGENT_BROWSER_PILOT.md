# Agent Browser Pilot (Option 1)

This pilot keeps `agent-browser` as an optional, scoped tool for browser-specific tasks without changing core ZHC-Nova architecture.

## Pilot Goal

- Validate whether `vercel-labs/agent-browser` improves browser task reliability while preserving current approval/review controls.

## Scope (Phase 1)

- Browser-only tasks (navigation, snapshots, form interactions, screenshots).
- No purchases, no account settings changes, no destructive web actions.
- All runs remain under existing `plan -> review -> approve -> resume` gate flow.

## Safety Defaults

Use these flags/environment defaults in all pilot runs:

- `--allowed-domains <comma-list>`
- `--confirm-actions eval,download`
- `--max-output 50000`
- `--json`
- unique `--session-name` per task

Recommended env variables:

```bash
AGENT_BROWSER_CONTENT_BOUNDARIES=1
AGENT_BROWSER_MAX_OUTPUT=50000
AGENT_BROWSER_CONFIRM_ACTIONS=eval,download
```

## Success Criteria

- No policy bypasses through browser command path.
- No duplicate execution in resume/idempotency flow.
- Pilot task success rate >= 95% over 20+ browser tasks.
- No unapproved sensitive actions.

## Exit Conditions

- Keep as optional backend if criteria are met.
- Roll back pilot if any approval-control regression appears.
