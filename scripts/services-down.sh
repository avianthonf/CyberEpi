#!/usr/bin/env bash
for s in user-service symptom-service prescription-service notification-service epi-engine privacy-service; do
  podman rm -f "cyberepi-$s" 2>/dev/null || true
  pkill -f "uvicorn src.main:app --port 800[1-6]" 2>/dev/null || true
done
