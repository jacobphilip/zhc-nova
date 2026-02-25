# ZHC-Nova Roadmap

## v1 - Safe Single-Node Foundation (this scaffold)

- Task registry in SQLite with events + approvals
- Rule-based task routing (PI_LIGHT vs UBUNTU_HEAVY)
- Telegram command contract (stub runtime)
- OpenCode wrapper + Pi-to-Ubuntu dispatch wrapper
- Policy-driven approval gates
- Baseline systemd templates and bootstrap scripts

## v1.1 - Telegram Runtime Online

- Implement real Telegram bot/webhook polling service
- Map commands to router actions and task board views
- Persist chat/session metadata and command audit events
- Add outbound guardrails for customer-facing channels

## v1.2 - ZeroClaw Scheduling + Workflows

- Real scheduled workflows and profile-based orchestration
- Execution retries, backoff, dead-letter handling
- Expanded worker channels and better local Pi task handling

## v1.3 - Data Governance Hardening

- Protected records workflow and finalization controls
- Compliance artifact lifecycle and immutable summary exports
- Vault mirror sync and integrity verification

## v2 - Multi-Pi Swarm + Fleet Policy

- Multi-node worker registration and health-based routing
- Queue-aware dispatch and node capacity policy
- Distributed status board with role-specific visibility

## v2.5 - Advanced Model Routing

- OpenRouter planner/reviewer/summarizer roles by policy
- Provider fallback chains and outage-aware rerouting
- Cost/latency-aware dynamic model selection

## v3 - Full Operations Platform

- Web dashboard complementing Telegram control plane
- Rich incident management + playbooks
- Pluggable business modules beyond farm ops
