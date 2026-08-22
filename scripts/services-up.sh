#!/usr/bin/env bash
# Fixed service startup script with proper log paths and graceful shutdown

set -euo pipefail

# Trap to handle graceful shutdown
cleanup() {
    echo "Shutting down services gracefully..."
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    wait
    echo "All services stopped"
}
trap cleanup EXIT INT TERM

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
    cd "services/$svc"
    exec uvicorn src.main:app --host 127.0.0.1 --port "$port"
  ) > "$(pwd)/logs/${svc}.log" 2>&1 &
  pids+=("$!")
done

echo "Started PIDs: ${pids[*]}"
echo "Tail logs with: tail -f logs/*.log"
echo "Press Ctrl+C to stop all services"

# Wait for all background processes
wait
