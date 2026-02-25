# Security

## Secrets Handling

- Do not commit real secrets.
- Use `.env` locally and keep `.env.example` sanitized.
- Treat exposed tokens as compromised and rotate immediately.

## Access Boundaries

- `storage/records/`: official/protected records only.
- `storage/memory/`: assistant memory (non-record operational context).
- `storage/tasks/`: runtime artifacts and logs.
- `storage/vault-mirror/`: secure mirror staging area.

## Approval Gates (default required)

- git push
- deploy/restart
- file deletion
- scheduler changes
- compliance/spray record finalization
- customer-facing outbound messages

Approval policy is defined in `shared/policies/approvals.yaml`.

## Network and Runtime Safety

- No automatic deploy actions in v1.
- No destructive shell actions without explicit approval.
- SSH dispatch commands should use least-privilege runtime accounts.

## Execution Policy Layer

- Execution policy is loaded from `shared/policies/execution_policy.yaml` (override with `ZHC_EXECUTION_POLICY`).
- Enforcement mode is `strict` by default (override with `ZHC_POLICY_ENFORCEMENT=warn|strict`).
- In `strict`, router blocks tasks before dispatch when:
  - task type is not in the route-class allowlist
  - prompt includes blocked policy keywords
  - prompt includes blocked path patterns
- Policy blocks are not overrideable via `/approve`; they require policy/config change.
- Wrapper scripts (`zrun.sh`, `zdispatch.sh`) apply keyword checks as defense-in-depth.

## TODO

- TODO: REAL_INTEGRATION - secret manager/vault integration.
- TODO: REAL_INTEGRATION - command signing/verification for control plane.
