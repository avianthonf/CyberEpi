#!/usr/bin/env bash
set -e
NET=cyberepi-net
# Map service to its port
declare -A PORTS=(
  [user-service]=8001
  [symptom-service]=8002
  [prescription-service]=8003
  [notification-service]=8004
  [epi-engine]=8005
  [privacy-service]=8006
)
for svc in ${!PORTS[@]}; do
  port=${PORTS[$svc]}
  echo "Starting $svc on :$port"
  podman rm -f "cyberepi-$svc" || true
  # Note: Some services might fail if env is not correct (e.g. KAFKA_BOOTSTRAP_SERVERS)
  # I'll re-use COMMON_ENV from services-up.sh
  podman run -d --name "cyberepi-$svc" --network "$NET" -p "127.0.0.1:$port:$port" \
    -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
    -e DATABASE_URL="postgresql+asyncpg://cyberepi:devpassword@postgres:5432/cyberepi" \
    -e REDIS_URL="redis://redis:6379/0" \
    "localhost/infra_$svc:latest"
done
