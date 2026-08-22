#!/usr/bin/env bash
set -e
echo "Starting infra with host loopback mapping..."
podman run -d --name cyberepi-postgres -p 127.0.0.1:5432:5432 \
    --health-cmd="pg_isready -U postgres" --health-interval=2s --health-retries=10 \
    -e POSTGRES_PASSWORD=devpassword -e POSTGRES_DB=cyberepi timescale/timescaledb:latest-pg16

echo "Waiting for postgres..."
while [ "$(podman inspect cyberepi-postgres --format='{{.State.Health.Status}}')" != "healthy" ]; do
    sleep 2
done

podman exec -i cyberepi-postgres psql -U postgres -d postgres < infra/postgres-init/00-init-pg.sql
podman run -d --name cyberepi-redis -p 127.0.0.1:6379:6379 redis:7-alpine
podman run -d --name cyberepi-kafka -p 127.0.0.1:9092:9092 \
    -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:29093 \
    -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:29093 \
    -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://127.0.0.1:9092 \
    -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER -e CLUSTER_ID=MkU3OEVBNTcwNTJENDM2Qo \
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
    confluentinc/cp-kafka:7.6.0
podman run -d --name cyberepi-keycloak -p 127.0.0.1:8080:8080 \
    -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin -e KC_DB=postgres \
    -e KC_DB_URL=jdbc:postgresql://host.containers.internal:5432/keycloak \
    quay.io/keycloak/keycloak:24.0 start-dev
