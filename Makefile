.PHONY: init-dev init-pi db-init healthcheck demo-heavy demo-light list

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
