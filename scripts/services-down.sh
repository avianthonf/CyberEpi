#!/usr/bin/env bash
# Stop services started by services-up.sh
# Uses port-based detection with CWD validation for safety

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Stopping CyberEpi services..."

# Kill uvicorn processes for ports 8001-8006, verifying they're in this repo
killed=0
for port in 8001 8002 8003 8004 8005 8006; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    cwd=$(readlink /proc/$pid/cwd 2>/dev/null || echo "")
    if [[ "$cwd" == "$REPO_ROOT" || "$cwd" == "$REPO_ROOT/"* ]]; then
      echo "  Killing process $pid on port $port"
      kill -TERM "$pid" 2>/dev/null || true
      killed=$((killed + 1))
    fi
  done
done

if [[ $killed -eq 0 ]]; then
  echo "No running services found"
  exit 0
fi

# Wait briefly for graceful shutdown
sleep 2

# Force kill any remaining
for port in 8001 8002 8003 8004 8005 8006; do
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    cwd=$(readlink /proc/$pid/cwd 2>/dev/null || echo "")
    if [[ "$cwd" == "$REPO_ROOT" || "$cwd" == "$REPO_ROOT/"* ]]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
done

echo "Services stopped"
