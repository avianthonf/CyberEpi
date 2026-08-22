"""Negative-path verification: auth gates, role gates, and input validation.

Complements scripts/verify_all.py (positive paths). Every check expects a
REJECTION; any 2xx here is a regression.
"""
from __future__ import annotations

import random
import string
import sys

import requests

from verify_all import SERVICES, get_user_token, reg_user, step

EPI = SERVICES["epi"]
PRI = SERVICES["privacy"]
SYM = SERVICES["symptom"]
RX = SERVICES["prescription"]

failures = 0


def expect(name: str, r: requests.Response, codes: tuple[int, ...], note: str = "") -> None:
    ok = r.status_code in codes
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}: HTTP {r.status_code} (expect {codes}) {note}")
    if not ok:
        global failures
        failures += 1


def main() -> int:
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    uname, pwd, patient_id, _ = reg_user(suffix)  # patient role only, NO physician
    ptok = get_user_token(uname, pwd)
    pat = {"Authorization": f"Bearer {ptok}"}
    region = "region-verify"

    print("== Unauthenticated (no token): expect 401 ==")
    # NOTE: GET /api/v1/regions/{id}/params is an intentional public read for the
    # patient app (SEIR params, no PII) — see docstring in params.py. Not gated.
    expect("GET epi /regions/{r}/forecast", requests.get(f"{EPI}/api/v1/regions/{region}/forecast", timeout=5), (401,))
    expect("GET epi /regions/{r}/state", requests.get(f"{EPI}/api/v1/regions/{region}/state", timeout=5), (401,))
    expect("GET epi /control/recommendations", requests.get(f"{EPI}/api/v1/control/recommendations", params={"region_id": region}, timeout=5), (401,))
    expect("GET epi /control/weights/{r}", requests.get(f"{EPI}/api/v1/control/weights/{region}", timeout=5), (401,))
    expect("GET epi /map/hotspots", requests.get(f"{EPI}/api/v1/map/hotspots", params={"region_id": region}, timeout=5), (401,))
    expect("GET symptom /v1/risk/score/{pid}", requests.get(f"{SYM}/v1/risk/score/{patient_id}", timeout=5), (401,))
    expect("POST symptom /v1/risk/deterioration", requests.post(f"{SYM}/v1/risk/deterioration", json={}, timeout=5), (401,))
    expect("GET privacy /fl/model/1", requests.get(f"{PRI}/api/v1/fl/model/1", timeout=5), (401,))
    expect("POST privacy /internal/dp/publish", requests.post(f"{PRI}/internal/dp/publish", json={"region_id": region, "stat_type": "count", "value": 1, "epsilon": 1.0}, timeout=5), (401,))
    expect("POST privacy /internal/dp/gaussian", requests.post(f"{PRI}/internal/dp/gaussian", json={"value": 1.0, "epsilon": 1.0, "delta": 1e-5, "sensitivity": 1.0}, timeout=5), (401,))

    print("\n== Patient role (no physician/admin): expect 403 ==")
    expect("PUT epi params", requests.put(f"{EPI}/api/v1/regions/{region}/params", headers=pat, json={"region_id": region, "N_pop": 1000, "beta": 0.4, "gamma": 0.1, "sigma": 0.2, "mu": 0.05, "alpha": 0.1, "delta": 0.05, "rho": 0.5, "gamma_A": 0.1, "gamma_M": 0.1, "gamma_S": 0.1, "gamma_H": 0.05, "gamma_ICU": 0.02, "h_rate": 0.05, "mu_icu": 0.05, "papp": 0.4, "fA": 0.3, "fM": 0.4, "fS": 0.3, "source": "manual_override"}, timeout=10), (403,))
    expect("POST epi control weights", requests.post(f"{EPI}/api/v1/control/weights/{region}", headers=pat, json={"C1": 1.0, "C2": 1.0, "C3": 1.0, "C4": 1.0, "W_u1": 0.5, "W_u2": 0.5, "W_u3": 0.5, "ethical_framework": "utilitarian"}, timeout=10), (403,))
    expect("PUT epi control weights", requests.put(f"{EPI}/api/v1/control/weights/{region}", headers=pat, json={"C1": 1.0, "C2": 1.0, "C3": 1.0, "C4": 1.0, "W_u1": 0.5, "W_u2": 0.5, "W_u3": 0.5, "ethical_framework": "utilitarian"}, timeout=10), (403,))
    expect("POST fl/trigger_aggregation", requests.post(f"{PRI}/api/v1/fl/trigger_aggregation", headers=pat, timeout=10), (403,))
    other_pid = "00000000-0000-0000-0000-00000000dead"
    expect("GET risk score of other patient", requests.get(f"{SYM}/v1/risk/score/{other_pid}", headers=pat, timeout=5), (403,))
    expect("POST mobility/upload as patient", requests.post(f"{EPI}/api/v1/mobility/upload", params={"region_id": region}, headers=pat, files={"file": ("m.csv", b"from_patch_id,to_patch_id,fraction\nA,B,0.5\n", "text/csv")}, timeout=10), (403,))

    print("\n== Staff (physician) allowed ==")
    from verify_all import get_admin_token, grant_physician_role

    admin = get_admin_token()
    grant_physician_role(uname, admin)
    ptok = get_user_token(uname, pwd)
    pat = {"Authorization": f"Bearer {ptok}"}
    expect("PUT control weights as physician", requests.put(f"{EPI}/api/v1/control/weights/{region}", headers=pat, json={"C1": 1.0, "C2": 1.0, "C3": 1.0, "C4": 1.0, "W_u1": 0.5, "W_u2": 0.5, "W_u3": 0.5, "ethical_framework": "utilitarian"}, timeout=60), (200, 201))

    print("\n== Input validation: expect 400/422 ==")
    expect("dp/gaussian negative epsilon", requests.post(f"{PRI}/internal/dp/gaussian", headers=pat, json={"value": 1.0, "epsilon": -1.0, "delta": 1e-5, "sensitivity": 1.0}, timeout=5), (400, 422))
    expect("dp/publish negative epsilon", requests.post(f"{PRI}/internal/dp/publish", headers=pat, json={"region_id": region, "stat_type": "count", "value": 1, "epsilon": -1.0}, timeout=5), (400, 422))
    # NaN payloads – json.dumps emits NaN literal; FastAPI/pydantic must reject
    nan_body = b'{"value": 1.0, "epsilon": NaN, "delta": 1e-5, "sensitivity": 1.0}'
    expect("dp/gaussian NaN epsilon", requests.post(f"{PRI}/internal/dp/gaussian", headers={**pat, "Content-Type": "application/json"}, data=nan_body, timeout=5), (400, 422))
    grad_nan = ('{"user_id": "%s", "round_id": 1, "gradient": [0.1, NaN, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1], "n_samples": 10}' % patient_id).encode()
    expect("fl/upload_gradient NaN element", requests.post(f"{PRI}/api/v1/fl/upload_gradient", headers={**pat, "Content-Type": "application/json"}, data=grad_nan, timeout=5), (400, 422))
    expect("prescription oversize drug_name", requests.post(f"{RX}/api/v1/prescriptions", headers=pat, json={"patient_id": patient_id, "drug_name": "X" * 300, "dosage": "1 mg", "frequency": "daily", "start_date": "2026-08-22"}, timeout=5), (400, 422))

    print(f"\n{'ALL NEGATIVE CHECKS PASSED' if failures == 0 else f'FAILURES: {failures}'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
