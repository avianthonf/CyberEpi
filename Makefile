all: up

up:
	bash scripts/podman-up.sh
	bash scripts/services-up.sh

down:
	bash scripts/services-down.sh
	podman-compose -f infra/docker-compose.yml down

smoke:
	python3 scripts/smoke.py

logs:
	tail -f logs/*.log

status:
	bash scripts/services-status.sh
