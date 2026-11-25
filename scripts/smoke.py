"""Smoke test for all running CyberEpi services.

Exits 0 only when every service responds 200 on /health and /metrics
within the per-request timeout. Designed to be runnable from a fresh
checkout against services started via scripts/services-up.sh.
"""

import argparse
import os
import sys
import time

import requests

SERVICE_PORT_OFFSET = int(os.environ.get("SERVICE_PORT_OFFSET", "0"))
DEFAULT_SERVICES = {
    name: os.environ.get(environment_variable, f"http://127.0.0.1:{port + SERVICE_PORT_OFFSET}").rstrip("/")
    for name, environment_variable, port in (
        ("user-service", "USER_SERVICE_URL", 8001),
        ("symptom-service", "SYMPTOM_SERVICE_URL", 8002),
        ("prescription-service", "PRESCRIPTION_SERVICE_URL", 8003),
        ("notification-service", "NOTIFICATION_SERVICE_URL", 8004),
        ("epi-engine", "EPI_ENGINE_URL", 8005),
        ("privacy-service", "PRIVACY_SERVICE_URL", 8006),
    )
}


def check_service(name, url, timeout=2.0):
    """Return (ok, message). ok=True iff /health and /metrics both 200."""
    for path in ("/health", "/metrics"):
        try:
            r = requests.get(f"{url}{path}", timeout=timeout)
        except requests.RequestException as e:
            return False, f"{path} check exception: {e}"
        if r.status_code != 200:
            return False, f"{path} check failed: HTTP {r.status_code}"
    return True, "passed /health and /metrics"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retries", type=int, default=1, help="Retry each service this many times before failing.")
    parser.add_argument("--timeout", type=float, default=2.0, help="Per-request timeout in seconds.")
    args = parser.parse_args()

    all_passed = True
    for name, url in DEFAULT_SERVICES.items():
        ok, msg = False, "no attempts"
        for _ in range(args.retries):
            ok, msg = check_service(name, url, timeout=args.timeout)
            if ok:
                break
            time.sleep(0.5)
        marker = "PASS" if ok else "FAIL"
        print(f"{name:25} {marker} ({msg})")
        if not ok:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
