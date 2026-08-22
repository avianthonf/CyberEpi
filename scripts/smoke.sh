#!/usr/bin/env bash
# Wrapper for smoke.py — uses system python (no venv dep) so it works
# even before services are running.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/smoke.py" "$@"
