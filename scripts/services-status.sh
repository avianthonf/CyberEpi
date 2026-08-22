#!/usr/bin/env bash
# CyberEpi — show status of all 6 services (container form) and /health.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

declare -A PORTS=(
  [user-service]=8001
  [symptom-service]=8002
  [prescription-service]=8003
  [notification-service]=8004
  [epi-engine]=8005
  [privacy-service]=8006
)

for svc in user-service symptom-service prescription-service notification-service epi-engine privacy-service; do
  port=${PORTS[$svc]}
  container="cyberepi-$svc"
  state=$(podman inspect --format '{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
  health=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}/health" 2>/dev/null || echo "—")
  printf "  %-22s container=%-10s /health=%s\n" "$svc" "$state" "$health"
done
