COMPOSE ?= podman-compose
PROJECT ?= cyberepi-singlehost
ENV_FILE ?= .env.production
PYTHON ?= .venv/bin/python

COMPOSE_COMMAND = $(COMPOSE) --env-file "$(ENV_FILE)" -p "$(PROJECT)" -f docker-compose.prod.yml

.PHONY: all prepare build up down logs status

all: up

prepare:
	bash scripts/prepare-deploy.sh "$(ENV_FILE)"

build:
	$(COMPOSE_COMMAND) build

up:
	$(COMPOSE_COMMAND) up -d --build --force-recreate

down:
	$(COMPOSE_COMMAND) down

smoke:
	$(PYTHON) scripts/smoke.py

logs:
	$(COMPOSE_COMMAND) logs -f

status:
	$(COMPOSE_COMMAND) ps
