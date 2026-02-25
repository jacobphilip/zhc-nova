.PHONY: init-dev init-pi db-init healthcheck demo-heavy demo-light list audit metrics telegram zeroclaw-preflight user-services smoke-fast test-control

init-dev:
	./scripts/init_dev.sh

init-pi:
	./scripts/init_pi.sh

db-init:
	./scripts/db_init.sh

healthcheck:
	./scripts/healthcheck.sh

demo-heavy:
	python3 services/task-router/router.py route --task-type code_refactor --prompt "Refactor irrigation advisory service"

demo-light:
	python3 services/task-router/router.py route --task-type ping --prompt "Check runtime status"

list:
	python3 shared/task-registry/task_registry.py list --limit 20

audit:
	python3 scripts/audit_score.py --scores docs/audits/latest_scores.json --output docs/audits/latest_report.md --iteration latest

metrics:
	python3 scripts/metrics_report.py --days 7 --iteration latest --output-json docs/audits/metrics/latest_metrics.json --output-md docs/audits/metrics/latest_metrics.md

telegram:
	python3 services/telegram-control/bot_longpoll.py

zeroclaw-preflight:
	./scripts/zeroclaw_preflight.sh

user-services:
	./scripts/install_user_services.sh

smoke-fast:
	python3 scripts/smoke_fast_control_plane.py --mode full

test-control:
	python3 tests/test_control_plane_invariants.py && python3 tests/test_dispatch_lease_recovery.py
