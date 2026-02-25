# Deployment on Raspberry Pi 5 (ARM64 Runtime)

## Target

- Raspberry Pi 5 (ARM64)
- Python 3.11+
- SSH connectivity to Ubuntu node for heavy tasks
- systemd for always-on services

## Setup

```bash
cp .env.example .env
./scripts/init_pi.sh
./scripts/db_init.sh
./scripts/healthcheck.sh
```

## Runtime Role

- Receive Telegram commands (future runtime integration)
- Run `services/task-router/router.py`
- Execute `PI_LIGHT` tasks locally
- Dispatch `UBUNTU_HEAVY` tasks through `infra/opencode/wrappers/zdispatch.sh`

## systemd Templates

- `infra/zeroclaw/systemd/zeroclaw-gateway.service`
- `infra/zeroclaw/systemd/zhc-task-router.service`

Copy and adjust paths/user values before enabling.

## TODO Integration Hooks

- TODO: REAL_INTEGRATION - Telegram runtime process (bot polling/webhook).
- TODO: REAL_INTEGRATION - ZeroClaw service hooks.
