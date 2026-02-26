# ZHC Agent Skills Spec (v0)

This document defines a lightweight skills format for ZHC-Nova, aligned with the public Agent Skills pattern while preserving Nova policy and approval gates.

## Purpose

- Make repeatable task procedures portable and easy to review.
- Keep skill behavior constrained by existing execution policy.
- Allow gradual migration toward skills-based worker capabilities.

## Directory Layout

Each skill lives in its own folder under `skills/`:

```text
skills/<skill-name>/
  SKILL.md
  scripts/         # optional
  resources/       # optional
  examples/        # optional
```

## Required SKILL.md Frontmatter

```yaml
---
name: browser-pilot-safe
description: Safe browser automation workflow for approved domains.
owner: zhc-nova
version: 0.1.0
risk_level: medium
requires_approval: true
required_gates:
  - plan
  - review_pass
  - approve
allowed_tools:
  - agent-browser
  - task_registry
forbidden_actions:
  - purchases
  - account_deletion
  - credential_export
---
```

Required keys:

- `name`
- `description`
- `risk_level` (`low|medium|high`)
- `requires_approval` (`true|false`)
- `required_gates` (list)
- `allowed_tools` (list)

## Runtime Rules

- Skills do not bypass router policy (`shared/policies/execution_policy.yaml`).
- For `requires_approval: true`, task execution must still follow `plan -> review -> approve -> resume`.
- Skill instructions can narrow permissions, never broaden them.
- High-risk actions remain blocked unless explicitly approved by existing governance paths.

## Authoring Guidelines

- Keep instructions procedural and deterministic.
- Include clear stop conditions and rollback notes.
- Prefer explicit command snippets over vague language.
- List tool constraints and allowed domains when browser/network actions exist.

## Compatibility Notes

- Inspired by patterns used in:
  - `anthropics/skills`
  - `kepano/obsidian-skills`
- ZHC-Nova currently uses an internal skills directory and does not auto-load external marketplaces.
