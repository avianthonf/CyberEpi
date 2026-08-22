#!/usr/bin/env bash
# CyberEpi — create the local Python venv and install the 6 services + libs.
#
# Idempotent. Uses the system python3 (3.12+); arm64 is fine.
# Installs services in editable mode so src/ changes don't need reinstalls.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"
VENV="${REPO_ROOT}/.venv"

if [ ! -x "${VENV}/bin/python" ]; then
  echo "creating venv at ${VENV}"
  "$PY" -m venv "$VENV"
fi

PIP="${VENV}/bin/pip"
PIP_FLAGS=(--quiet --disable-pip-version-check)

echo "upgrading pip"
"$PIP" install "${PIP_FLAGS[@]}" --upgrade pip wheel setuptools

echo "installing libs/seir-core"
"$PIP" install "${PIP_FLAGS[@]}" -e ./libs/seir-core

echo "installing libs/shared"
"$PIP" install "${PIP_FLAGS[@]}" -e ./libs/shared

echo "installing services"
for svc in user-service symptom-service prescription-service notification-service epi-engine privacy-service; do
  echo "  - ${svc}"
  "$PIP" install "${PIP_FLAGS[@]}" -e "./services/${svc}" 2>&1 | tail -5
done

echo
echo "done. activate with:  source .venv/bin/activate"
