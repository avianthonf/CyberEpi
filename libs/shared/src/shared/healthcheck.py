#!/usr/bin/env python3
"""Container healthcheck — polls the service's /health endpoint.

Usage: python healthcheck.py   (reads SERVICE_PORT or defaults to 8000)
"""

import os
import sys
import time

import httpx


def main() -> int:
    port = os.getenv("SERVICE_PORT", "8000")
    url = f"http://localhost:{port}/health"
    for _ in range(30):
        try:
            resp = httpx.get(url, timeout=3.0)
            if resp.status_code == 200:
                print("Health check passed")
                return 0
            print(f"Health check failed with status: {resp.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"Health check failed: {e}")
        time.sleep(1)
    return 1


if __name__ == "__main__":
    sys.exit(main())
