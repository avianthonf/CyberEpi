#!/usr/bin/env bash
# Fixed service startup script with proper log paths and graceful shutdown

set -euo pipefail

# Trap to handle graceful shutdown
cleanup() {
    local reason=$1
    if [[ $reason == signal ]]; then
        echo "Shutting down services gracefully..."
    fi
    for pid in "${pids[@]:-}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    wait
    if [[ $reason == signal ]]; then
        echo "All services stopped"
    fi
}
trap 'cleanup signal' EXIT INT TERM

# Preflight: refuse to start services until infra is reachable, so a slow or
# half-up stack produces a clear error instead of six silent startup crashes.
wait_tcp() {
  local name=$1 host=$2 port=$3 tries=${4:-30}
  for _ in $(seq 1 "$tries"); do
    if (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; then
      echo "  ok $name reachable at $host:$port"
      return 0
    fi
    sleep 2
  done
  echo "error: $name not reachable at $host:$port after $((tries*2))s — run scripts/podman-up.sh first" >&2
  exit 1
}
wait_tcp postgres 127.0.0.1 5432
wait_tcp redis    127.0.0.1 6379
wait_tcp kafka    127.0.0.1 9092
wait_tcp keycloak 127.0.0.1 8080

# Use the established venv
if [[ ! -f .venv/bin/activate ]]; then
  echo "error: .venv/bin/activate not found — run scripts/setup-venv.sh first" >&2
  exit 1
fi
source .venv/bin/activate

# Create logs directory at project root
mkdir -p logs

# Environment configuration
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://cyberepi:devpassword@127.0.0.1:5432/cyberepi}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-127.0.0.1:9092}"
export KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-cyberepi-services}"
export KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-vYAGNs16yR2ClbFVDkaAwY0qOr7K7k0y}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

declare -A PORTS=(
  [user-service]=8001
  [symptom-service]=8002
  [prescription-service]=8003
  [notification-service]=8004
  [epi-engine]=8005
  [privacy-service]=8006
)

pids=()
for svc in "${!PORTS[@]}"; do
  port="${PORTS[$svc]}"
  echo "Starting $svc on :$port"
  (
    cd "services/$svc" || exit 1
    exec uvicorn src.main:app --host 127.0.0.1 --port "$port"
  ) > "$(pwd)/logs/${svc}.log" 2>&1 &
  pids+=("$!")
done

echo "Started PIDs: ${pids[*]}"
echo "Tail logs with: tail -f logs/*.log"
echo "Press Ctrl+C to stop all services"

# Give every service a moment, then fail loudly if any died at startup
# (bad env, DB migration crash, port conflict) instead of "waiting" forever.
sleep 5
failed=0
for i in "${!pids[@]}"; do
  if ! kill -0 "${pids[$i]}" 2>/dev/null; then
    echo "error: a service exited during startup — check logs/" >&2
    failed=1
  fi
done
((failed)) && exit 1

# Wait for all background processes; report which one took the script down.
set +e
wait -n; rc=$?
echo "A service exited (rc=$rc); shutting down the rest. Recent log tails:" >&2
for svc in "${!PORTS[@]}"; do
  echo "--- $svc ---" >&2
  tail -n 5 "logs/${svc}.log" >&2 || true
done
exit "$rc"

