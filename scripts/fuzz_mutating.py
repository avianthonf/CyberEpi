"""Fuzz every mutating endpoint: invariant is NO 5xx / no hang, for any input.

Covers, per endpoint:
  - baseline valid body (sanity)
  - each top-level field replaced with adversarial values
    ("", None, -1, 1e308, 9**999, 20k-char string, [], {})
  - structural: body as list/string/null, malformed JSON, wrong Content-Type,
    unknown extra field
  - JSON with NaN/Infinity literals (raw body)
  - path-param fuzz on parameterized routes (traversal, huge, quote, NUL)

Exit 0 iff zero 5xx responses observed.
"""
from __future__ import annotations

import json
import sys

import requests

from verify_all import (
    SERVICES,
    get_admin_token,
    get_user_token,
    grant_physician_role,
    reg_user,
)

REGION = "region-fuzz"
TIMEOUT = 15

ADVERSARIAL: list[tuple[str, object]] = [
    ("empty-str", ""),
    ("null", None),
    ("neg", -1),
    ("huge-f", 1e308),
    ("huge-i", 9**999),
    ("long-str", "A" * 20000),
    ("list", []),
    ("dict", {}),
]

failures: list[str] = []
results: list[tuple[str, str, int]] = []


def record(label: str, r: requests.Response | None, err: Exception | None = None) -> None:
    if r is None:
        failures.append(f"{label}: EXCEPTION {err}")
        print(f"  FAIL {label}: EXCEPTION {err}")
        return
    results.append((label, "", r.status_code))
    if r.status_code >= 500:
        failures.append(f"{label}: HTTP {r.status_code} body={r.text[:160]}")
        print(f"  FAIL {label}: HTTP {r.status_code} {r.text[:120]}")


def post(method: str, url: str, label: str, headers: dict, body=None, raw=None) -> None:
    try:
        if raw is not None:
            r = requests.request(
                method, url, headers={**headers, "Content-Type": "application/json"},
                data=raw, timeout=TIMEOUT,
            )
        else:
            r = requests.request(method, url, headers=headers, json=body, timeout=TIMEOUT)
        record(label, r)
    except Exception as e:  # noqa: BLE001
        record(label, None, e)


def fuzz_endpoint(label: str, method: str, url: str, headers: dict, valid: dict) -> None:
    print(f"- {label}")
    post(method, url, f"{label} baseline", headers, body=valid)
    for field in list(valid.keys()):
        for vname, v in ADVERSARIAL:
            b = dict(valid)
            b[field] = v
            try:
                post(method, url, f"{label}.{field}={vname}", headers, body=b)
            except (ValueError, TypeError, OverflowError) as e:
                record(f"{label}.{field}={vname}", None, e)
    for sname, struct in [("list", []), ("str", "x"), ("null", None)]:
        post(method, url, f"{label} body={sname}", headers, body=struct)
    post(method, url, f"{label} body=malformed", headers, raw=b"{")
    post(method, url, f"{label} body=nan-lit", headers, raw=b'{"value": NaN, "epsilon": NaN}')
    b = dict(valid)
    b["__unknown__"] = "fuzzer"
    post(method, url, f"{label} extra-field", headers, body=b)
    try:
        r = requests.request(method, url, headers={**headers, "Content-Type": "text/plain"}, data="not json", timeout=TIMEOUT)
        record(f"{label} wrong-ctype", r)
    except Exception as e:  # noqa: BLE001
        record(f"{label} wrong-ctype", None, e)


PATH_FUZZ = ["../../../etc/passwd", "A" * 2000, "' OR '1'='1", "%00", "not-a-uuid"]


def fuzz_path_params(label: str, method: str, url_tmpl: str, headers: dict, body=None) -> None:
    for v in PATH_FUZZ:
        url = url_tmpl.replace("FUZZ", v)
        try:
            r = requests.request(method, url, headers=headers, json=body, timeout=TIMEOUT)
            record(f"{label} path={v[:16]}", r)
        except Exception as e:  # noqa: BLE001
            record(f"{label} path={v[:16]}", None, e)


def main() -> int:
    admin = get_admin_token()
    uname, pwd, patient_id, keycloak_id = reg_user("fuzzx")
    patient = {"Authorization": f"Bearer {get_user_token(uname, pwd)}"}
    pname, ppwd, ppat_id, _ = reg_user("fuzzd")
    grant_physician_role(pname, admin)
    staff = {"Authorization": f"Bearer {get_user_token(pname, ppwd)}"}

    U = SERVICES["user"]
    SY = SERVICES["symptom"]
    RX = SERVICES["prescription"]
    NO = SERVICES["notification"]
    EP = SERVICES["epi"]
    PR = SERVICES["privacy"]

    # --- user-service ---
    fuzz_endpoint("register", "POST", f"{U}/api/v1/auth/register", {}, {
        "email": "fz_base@example.com", "password": "Fuzz-Str0ng!123",
        "first_name": "F", "last_name": "Z", "region_id": REGION,
    })
    fuzz_endpoint("put-patient", "PUT", f"{U}/api/v1/patients/{patient_id}", patient,
                  {"first_name": "VerifyUpd", "phone": "+1-555-0100"})
    fuzz_endpoint("push-token", "POST", f"{U}/api/v1/patients/{patient_id}/push_token", patient,
                  {"token": "tok-abc", "platform": "android"})

    # --- symptom-service ---
    fuzz_endpoint("post-symptoms", "POST", f"{SY}/api/v1/symptoms", patient, {
        "patient_id": patient_id, "symptoms": ["fever"], "temperature": 38.5,
        "heart_rate": 95, "spo2": 96.0, "systolic_bp": 120, "diastolic_bp": 80,
        "region_id": REGION,
    })
    fuzz_endpoint("risk-deterioration", "POST", f"{SY}/v1/risk/deterioration", patient, {
        "patient_id": patient_id, "age": 36, "days_since_onset": 3, "fever_duration_h": 24,
        "fever_max_24h": 38.8, "heart_rate_current": 95, "hr_slope_48h": 0.1,
        "local_hosp_rate": 0.05, "n_comorbidities": 0, "regional_Rt": 1.2,
        "risk_score_acceleration": 0.05, "risk_score_current": 0.6, "spo2_current": 96.0,
    })

    # --- prescription-service ---
    fuzz_endpoint("post-prescription", "POST", f"{RX}/api/v1/prescriptions", staff, {
        "patient_id": patient_id, "drug_name": "Acetaminophen", "dosage": "500 mg",
        "frequency": "every 6 hours", "start_date": "2026-08-22", "end_date": "2026-08-30",
        "ndc_code": "50580-506-02", "rxnorm_id": "161", "notes": "fuzz",
    })
    fuzz_endpoint("put-rx-status", "PUT", f"{RX}/api/v1/prescriptions/00000000-0000-0000-0000-000000000000/status",
                  staff, {"status": "completed"})
    fuzz_endpoint("med-scan", "POST", f"{RX}/api/v1/medications/scan", patient,
                  {"ocr_text": "Acetaminophen 500 mg tablet", "patient_id": patient_id})

    # --- notification-service ---
    fuzz_endpoint("post-notification", "POST", f"{NO}/api/v1/notifications", patient, {
        "patient_id": patient_id, "type": "risk_alert", "title": "T",
        "body": "B", "priority": "high",
    })
    fuzz_endpoint("post-notif-send", "POST", f"{NO}/api/v1/notifications/send", patient,
                  {"patient_id": patient_id, "title": "T", "body": "B", "data": {"k": 1}})

    # --- epi-engine (staff) ---
    fuzz_endpoint("put-region-params", "PUT", f"{EP}/api/v1/regions/{REGION}/params", staff, {
        "region_id": REGION, "N_pop": 1000000,
        "beta": 0.4, "gamma": 0.1, "sigma": 0.2, "mu": 0.05,
        "alpha": 0.1, "delta": 0.05, "rho": 0.5,
        "gamma_A": 0.1, "gamma_M": 0.1, "gamma_S": 0.1, "gamma_H": 0.05, "gamma_ICU": 0.02,
        "h_rate": 0.05, "mu_icu": 0.05,
        "papp": 0.4, "fA": 0.3, "fM": 0.4, "fS": 0.3,
        "source": "manual_override",
    })
    fuzz_endpoint("post-control-weights", "POST", f"{EP}/api/v1/control/weights/{REGION}", staff, {
        "C1": 1.0, "C2": 1.0, "C3": 1.0, "C4": 1.0,
        "W_u1": 0.5, "W_u2": 0.5, "W_u3": 0.5,
        "ethical_framework": "utilitarian", "notes": "fuzz",
    })

    # --- privacy-service ---
    fuzz_endpoint("dp-gaussian", "POST", f"{PR}/internal/dp/gaussian", patient,
                  {"value": 100.0, "epsilon": 1.0, "delta": 1e-5, "sensitivity": 1.0})
    fuzz_endpoint("dp-publish", "POST", f"{PR}/internal/dp/publish", patient,
                  {"region_id": REGION, "stat_type": "count", "value": 42, "epsilon": 1.0})
    fuzz_endpoint("fl-upload", "POST", f"{PR}/api/v1/fl/upload_gradient", patient, {
        "user_id": patient_id, "round_id": 900,
        "gradient": [0.01] * 10, "n_samples": 100,
    })

    # --- mobility upload (multipart) ---
    print("- mobility-upload")
    for cname, content in [
        ("empty-file", b""),
        ("bad-header", b"nope,nope\n1,2\n"),
        ("huge-frac", b"from_patch_id,to_patch_id,fraction\nA,B,1e308\n"),
        ("nan-frac", b"from_patch_id,to_patch_id,fraction\nA,B,nan\n"),
        ("null-bytes", b"\x00\x00\x00\x00"),
        ("long-line", b"from_patch_id,to_patch_id,fraction\n" + ("A" * 50000).encode() + b",B,0.1\n"),
    ]:
        try:
            r = requests.post(
                f"{EP}/api/v1/mobility/upload", params={"region_id": REGION}, headers=staff,
                files={"file": ("f.csv", content, "text/csv")}, timeout=TIMEOUT,
            )
            record(f"mobility-upload {cname}", r)
        except Exception as e:  # noqa: BLE001
            record(f"mobility-upload {cname}", None, e)

    # --- path-param fuzz ---
    fuzz_path_params("get-patient", "GET", f"{U}/api/v1/patients/FUZZ", patient)
    fuzz_path_params("risk-score", "GET", f"{SY}/v1/risk/score/FUZZ", patient)
    fuzz_path_params("rx-status", "PUT", f"{RX}/api/v1/prescriptions/FUZZ/status", staff, {"status": "completed"})
    fuzz_path_params("region-state", "GET", f"{EP}/api/v1/regions/FUZZ/state", staff)

    print(f"\n===== {len(results) + len(failures)} requests =====")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
        return 1
    print("ALL FUZZ CHECKS PASSED (no 5xx)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
