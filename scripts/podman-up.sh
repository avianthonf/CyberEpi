#!/usr/bin/env bash
# CyberEpi — bring up the full stack on rootless podman.
#
# What this does:
#   1. Ensures the cyberepi-net bridge exists.
#   2. Starts Postgres (TimescaleDB), Redis, Zookeeper, Kafka (+ topics), Keycloak.
#   3. Waits for each container to report healthy.
#   4. Verifies connectivity (psql, redis-cli, kafka topics, keycloak realm).
#
# What this does NOT do (out of scope for Option A):
#   - Kong API gateway, Prometheus, Grafana, Loki, Promtail.
#   - Building the 6 microservice images. The Makefile target `services` runs
#     them as local uvicorn processes; `services-podman` runs them in containers.
#
# Usage:  scripts/podman-up.sh
set -euo pipefail

# Resolve repo root regardless of where the script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

NET=cyberepi-net
PG_VOL=cyberepi-pgdata
REDIS_VOL=cyberepi-redis-data
ZK_VOL=cyberepi-zk-data
ZK_LOG_VOL=cyberepi-zk-log
KAFKA_VOL=cyberepi-kafka-data

PASSWORD=devpassword

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail()  { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

# 1. network ─────────────────────────────────────────────────────────────
if ! podman network exists "$NET" >/dev/null 2>&1; then
  podman network create "$NET" >/dev/null
  ok "created network $NET"
else
  ok "network $NET already exists"
fi

# 2. volumes ────────────────────────────────────────────────────────────
for v in "$PG_VOL" "$REDIS_VOL" "$ZK_VOL" "$ZK_LOG_VOL" "$KAFKA_VOL"; do
  podman volume exists "$v" >/dev/null 2>&1 || podman volume create "$v" >/dev/null
done
ok "volumes ready"

# 3. containers ─────────────────────────────────────────────────────────
running() { podman ps --format '{{.Names}}' | grep -qx "cyberepi-$1"; }
health()  { podman inspect --format '{{.State.Health.Status}}' "cyberepi-$1" 2>/dev/null || echo none; }

ensure() {
  local name=$1; shift
  if running "$name"; then
    ok "$name already running"
    return
  fi
  podman rm -f "cyberepi-$name" >/dev/null 2>&1 || true
  bold "starting $name"
  "$@" >/dev/null
  ok "$name created"
}

# Note: aardvark-dns only registers the container's --name by default. We add
# --network-alias so other containers can reach the bare hostname (postgres,
# redis, zookeeper, kafka, keycloak) that env vars and config files reference.

ensure postgres \
  podman run -d --name cyberepi-postgres --network-alias postgres \
    --network "$NET" \
    -p 5432:5432 \
    -v "$PG_VOL":/var/lib/postgresql/data \
    -v "$REPO_ROOT/infra/postgres-init":/docker-entrypoint-initdb.d:ro \
    -e POSTGRES_DB=cyberepi \
    -e POSTGRES_USER=cyberepi \
    -e POSTGRES_PASSWORD="$PASSWORD" \
    --health-cmd "pg_isready -U cyberepi -d cyberepi" \
    --health-interval 5s --health-timeout 5s --health-retries 20 \
    --health-start-period 30s \
    docker.io/timescale/timescaledb:latest-pg16

ensure redis \
  podman run -d --name cyberepi-redis --network-alias redis \
    --network "$NET" \
    -p 6379:6379 \
    -v "$REDIS_VOL":/data \
    --health-cmd "redis-cli ping" \
    --health-interval 5s --health-timeout 3s --health-retries 10 \
    docker.io/redis:7-alpine \
    redis-server --save 60 1 --loglevel warning --maxmemory 256mb --maxmemory-policy allkeys-lru

# Note: `srvr` is enabled by default; `ruok` is not whitelisted in
# Confluent cp-zookeeper:7.6.0, so we use srvr.
ensure zookeeper \
  podman run -d --name cyberepi-zookeeper --network-alias zookeeper \
    --network "$NET" \
    -v "$ZK_VOL":/var/lib/zookeeper/data \
    -v "$ZK_LOG_VOL":/var/lib/zookeeper/log \
    -e ZOOKEEPER_CLIENT_PORT=2181 \
    -e ZOOKEEPER_TICK_TIME=2000 \
    --health-cmd "sh -c 'echo srvr | nc 127.0.0.1 2181 | grep -q Latency'" \
    --health-interval 5s --health-timeout 3s --health-retries 20 \
    --health-start-period 15s \
    docker.io/confluentinc/cp-zookeeper:7.6.0

ensure kafka \
  podman run -d --name cyberepi-kafka --network-alias kafka \
    --network "$NET" \
    -p 9092:9092 \
    -v "$KAFKA_VOL":/var/lib/kafka/data \
    -e KAFKA_BROKER_ID=1 \
    -e KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181 \
    -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092 \
    -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT \
    -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=false \
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
    -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
    --health-cmd "kafka-broker-api-versions --bootstrap-server localhost:9092" \
    --health-interval 10s --health-timeout 5s --health-retries 20 \
    --health-start-period 30s \
    docker.io/confluentinc/cp-kafka:7.6.0

# Note: KC24 doesn't expose /health or /health/ready; /realms/master returns
# 200 once Keycloak has fully initialized.
ensure keycloak \
  podman run -d --name cyberepi-keycloak --network-alias keycloak \
    --network "$NET" \
    -p 8080:8080 \
    -v "$REPO_ROOT/infra/keycloak-realms:/opt/keycloak/data/import:ro" \
    -e KEYCLOAK_ADMIN=admin \
    -e KEYCLOAK_ADMIN_PASSWORD=admin \
    -e KC_DB=postgres \
    -e KC_DB_URL=jdbc:postgresql://postgres:5432/keycloak \
    -e KC_DB_USERNAME=cyberepi \
    -e KC_DB_PASSWORD="$PASSWORD" \
    --health-cmd "sh -c 'exec 3<>/dev/tcp/127.0.0.1/8080; echo -e \"GET /realms/master HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n\" >&3; head -1 <&3 | grep -q 200'" \
    --health-interval 10s --health-timeout 5s --health-retries 30 \
    --health-start-period 90s \
    quay.io/keycloak/keycloak:24.0 start-dev --import-realm

# 4. wait for healthy ──────────────────────────────────────────────────
bold "waiting for containers to be healthy"
for name in postgres redis zookeeper kafka keycloak; do
  printf "  %-12s " "$name"
  for i in {1..150}; do
    status=$(health "$name")
    if [ "$status" = "healthy" ]; then
      printf "\033[32mhealthy\033[0m (%ds)\n" "$i"
      break
    fi
    sleep 2
    if [ "$i" = 150 ]; then
      printf "\033[31mTIMEOUT (last: %s)\033[0m\n" "$status"
      podman logs --tail 50 "cyberepi-$name" || true
      fail "$name never became healthy"
    fi
  done
done

# 5. create kafka topics ──────────────────────────────────────────────
if podman container exists cyberepi-kafka-init >/dev/null 2>&1; then
  podman rm -f cyberepi-kafka-init >/dev/null 2>&1 || true
fi
bold "creating kafka topics"
podman run --rm --network "$NET" \
  --name cyberepi-kafka-init --network-alias kafka-init \
  docker.io/confluentinc/cp-kafka:7.6.0 \
  bash -c '
    set -e
    cub kafka-ready -b kafka:9092 1 60
    for t in patient.events:6 epi.updates:3 alerts.push:3 symptom-reports:1; do
      name=${t%:*}; parts=${t#*:}
      kafka-topics --create --topic "$name" --partitions "$parts" --replication-factor 1 \
        --bootstrap-server kafka:9092 --if-not-exists
      echo "  ✓ $name ($parts partitions)"
    done
  '
ok "kafka topics ready"


bold "stack up. status:"
podman ps --filter "network=$NET" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
