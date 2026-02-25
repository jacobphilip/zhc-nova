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

- Receive Telegram commands via long-polling runtime (`services/telegram-control/bot_longpoll.py`)
- Run `services/task-router/router.py`
- Execute `PI_LIGHT` tasks locally
- Dispatch `UBUNTU_HEAVY` tasks through `infra/opencode/wrappers/zdispatch.sh`

## systemd Templates

- `infra/zeroclaw/systemd/zeroclaw-gateway.service`
- `infra/zeroclaw/systemd/zhc-task-router.service`
- `infra/zeroclaw/systemd/zhc-telegram-control.service`

Copy and adjust paths/user values before enabling.

Enable and start Telegram control service:

```bash
sudo cp infra/zeroclaw/systemd/zhc-telegram-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zhc-telegram-control.service
sudo systemctl status zhc-telegram-control.service
```

## Runtime Notes

- Long polling requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS`.
- Command audit log is written to `storage/memory/telegram_command_audit.jsonl`.
- Offset file is `storage/memory/telegram_offset.txt`.
- Runtime lock file is `storage/memory/telegram_longpoll.lock`.
- Show/reset offset:

```bash
python3 services/telegram-control/bot_longpoll.py --show-offset
python3 services/telegram-control/bot_longpoll.py --reset-offset
```
- TODO: REAL_INTEGRATION - ZeroClaw service hooks.
