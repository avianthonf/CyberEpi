"""CyberEpi end-to-end verification harness.

Exercises the main workflows of all six services using real Keycloak tokens
and live Kafka/Redis/Postgres backends.

SYNTHETIC DATA: All created users, symptoms, prescriptions, notifications, and
epidemiological records are synthetic demo data for verification only.

DATA MUTATIONS: This harness creates the following in the target stack:
- User accounts with Keycloak authentication (1 primary + N federated learning clients)
- Physician role grant via Keycloak admin API
- Epidemiological region parameters (PUT /api/v1/regions/{region}/params)
- Symptom reports and risk assessments
- Prescriptions (local CRUD operations)
- Notifications and push device token registrations
- Differential privacy operations (Gaussian noise, publish)
- Federated learning gradient uploads and model aggregation rounds

EXTERNAL API CALLS: By default, third-party API calls are skipped when credentials
or opt-in flags are absent:
- Medication validation (FDA/RxNorm): requires --include-external-lookups flag
- Push notification delivery: requires VERIFY_PUSH_TOKEN environment variable

Use --include-external-lookups to enable FDA/RxNorm medication validation.
Set VERIFY_PUSH_TOKEN to a valid device token for real push delivery testing.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import string
import sys
import time

import requests

# ---------- config ----------
KC_URL = os.environ.get("KEYCLOAK_URL", "http://127.0.0.1:8080").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "cyberepi")
ADMIN_TOKEN_URL = f"{KC_URL}/realms/master/protocol/openid-connect/token"
USER_TOKEN_URL = f"{KC_URL}/realms/{REALM}/protocol/openid-connect/token"
SERVICE_PORT_OFFSET = int(os.environ.get("SERVICE_PORT_OFFSET", "0"))
GATEWAY_URL = os.environ.get("GATEWAY_URL", f"http://127.0.0.1:{8000 + SERVICE_PORT_OFFSET}").rstrip("/")
SERVICES = {
    name: os.environ.get(environment_variable, f"http://127.0.0.1:{port + SERVICE_PORT_OFFSET}").rstrip("/")
    for name, environment_variable, port in (
        ("user", "USER_SERVICE_URL", 8001),
        ("symptom", "SYMPTOM_SERVICE_URL", 8002),
        ("prescription", "PRESCRIPTION_SERVICE_URL", 8003),
        ("notification", "NOTIFICATION_SERVICE_URL", 8004),
        ("epi", "EPI_ENGINE_URL", 8005),
        ("privacy", "PRIVACY_SERVICE_URL", 8006),
    )
}
TEST_USER_PASSWORD = os.environ.get("VERIFY_USER_PASSWORD", "password123!")
EPI_REGION = "region-verify"
# Authoritative backend risk tier enum from services/symptom-service/src/services/risk.py
VALID_RISK_TIERS = ("urgent", "consult", "moderate", "low")

results: list[tuple[str, str, bool, str]] = []
skipped_checks: list[str] = []
verification_push_token = os.environ.get("VERIFY_PUSH_TOKEN")


def step(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}: {detail}")
    results.append(("", name, ok, detail))


def svc_step(svc: str, name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {svc}/{name}: {detail}")
    results.append((svc, name, ok, detail))


def hr(title: str) -> None:
    print(f"\n=== {title} ===")


def get_admin_token() -> str:
    r = requests.post(
        ADMIN_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.environ.get("KEYCLOAK_ADMIN", "admin"),
            "password": os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin"),
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_user_token(username: str, password: str) -> str:
    r = requests.post(
        USER_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "cyberepi-patient-app",
            "username": username,
            "password": password,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def grant_physician_role(email: str, admin_token: str) -> None:
    """Assign the 'physician' realm role to a user (for epi-engine writes)."""
    r = requests.get(
        f"{KC_URL}/admin/realms/{REALM}/roles",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=5,
    )
    r.raise_for_status()
    roles = {rl["name"]: rl for rl in r.json()}
    physician = roles.get("physician")
    if not physician:
        raise RuntimeError("'physician' role not found in realm")
    r = requests.get(
        f"{KC_URL}/admin/realms/{REALM}/users",
        params={"email": email, "exact": "true"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=5,
    )
    r.raise_for_status()
    users = r.json()
    if not users:
        raise RuntimeError(f"User {email} not found")
    user_id = users[0]["id"]
    r = requests.post(
        f"{KC_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/realm",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        json=[physician],
        timeout=5,
    )
    if r.status_code not in (200, 204):
        raise RuntimeError(f"role assignment failed: {r.status_code} {r.text[:200]}")


def reg_user(suffix: str) -> tuple[str, str, str, str]:
    """Register a fresh user. Returns (email, password, patient_id, keycloak_id).

    patient_id is the local DB UUID; keycloak_id is the Keycloak UUID (the
    JWT `sub` claim, used for auth checks like the alerts stream).
    """
    uname = f"verify_{suffix}_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    pwd = TEST_USER_PASSWORD
    payload = {
        "email": f"{uname}@example.com",
        "password": pwd,
        "first_name": "Verify",
        "last_name": suffix.upper(),
        "region_id": EPI_REGION,
    }
    r = requests.post(
        f"{SERVICES['user']}/api/v1/auth/register",
        json=payload,
        timeout=15,
    )
    if r.status_code != 201:
        raise RuntimeError(f"register failed: {r.status_code} {r.text[:300]}")
    body = r.json()
    email = payload["email"]
    time.sleep(0.5)
    return email, pwd, body["id"], body["keycloak_id"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CyberEpi end-to-end verification harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  KEYCLOAK_URL          Keycloak base URL (default: http://127.0.0.1:8080)
  KEYCLOAK_REALM        Realm name (default: cyberepi)
  SERVICE_PORT_OFFSET   Add offset to default service ports (default: 0)
  VERIFY_USER_PASSWORD  Test user password (default: password123!)
  VERIFY_PUSH_TOKEN     Real device token for push delivery (optional, independent of --include-external-lookups)
  VERIFY_PUSH_PLATFORM  Push platform: android/ios (default: android)

Data mutations: This harness creates synthetic demo data including users,
prescriptions, notifications, and federated learning rounds.
        """,
    )
    parser.add_argument(
        "--include-external-lookups",
        action="store_true",
        help="Enable third-party API calls (FDA medication validation, RxNorm lookups). "
        "Default: skip external lookups for local-first/demo environments.",
    )
    args = parser.parse_args(argv)
    include_external = args.include_external_lookups

    print("CyberEpi verification harness starting...")
    if not include_external:
        print("  [INFO] External lookups disabled (use --include-external-lookups to enable)")

    # 1. Health checks
    hr("Health checks")
    for svc, base in SERVICES.items():
        try:
            r = requests.get(f"{base}/health", timeout=3)
            ok = r.status_code == 200 and r.json().get("status") == "healthy"
            svc_step(svc, "/health", ok, f"HTTP {r.status_code} {r.json().get('status')}")
        except Exception as e:
            svc_step(svc, "/health", False, str(e)[:120])

    # 2. Register + JWT
    hr("User registration + JWT")
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    try:
        admin_token = get_admin_token()
        step("admin-token", bool(admin_token), f"len={len(admin_token)}")
    except Exception as e:
        step("admin-token", False, str(e)[:200])
        return 1
    try:
        uname, pwd, patient_id, keycloak_id = reg_user(suffix)
        step("register", True, f"patient_id={patient_id}")
    except Exception as e:
        step("register", False, str(e)[:200])
        return 1
    try:
        user_token = get_user_token(uname, pwd)
        step("get-user-jwt", bool(user_token), f"len={len(user_token)}")
    except Exception as e:
        step("get-user-jwt", False, str(e)[:200])
        return 1
    # Grant physician role + re-fetch JWT (so epi PUT region params works).
    try:
        grant_physician_role(uname, admin_token)
        user_token = get_user_token(uname, pwd)
        step("grant-physician", True, "role=physician")
    except Exception as e:
        step("grant-physician", False, str(e)[:200])
    auth = auth_headers(user_token)
    region = EPI_REGION
    try:
        r = requests.put(
            f"{SERVICES['epi']}/api/v1/regions/{region}/params",
            headers=auth,
            json={
                "region_id": region,
                "N_pop": 1000000,
                "beta": 0.4,
                "gamma": 0.1,
                "sigma": 0.2,
                "mu": 0.05,
                "alpha": 0.1,
                "delta": 0.05,
                "rho": 0.5,
                "gamma_A": 0.1,
                "gamma_M": 0.1,
                "gamma_S": 0.1,
                "gamma_H": 0.05,
                "gamma_ICU": 0.02,
                "h_rate": 0.05,
                "mu_icu": 0.05,
                "papp": 0.4,
                "fA": 0.3,
                "fM": 0.4,
                "fS": 0.3,
                "source": "manual_override",
            },
            timeout=30,
        )
        svc_step("epi", "PUT region params", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "PUT region params", False, str(e)[:120])

    # ---- user-service ----
    hr("user-service")
    try:
        r = requests.get(f"{SERVICES['user']}/api/v1/patients/me", headers=auth, timeout=5)
        resolved_ok = r.status_code == 200
        resolved_id = r.json().get("id") if resolved_ok else None
        matches = resolved_id == patient_id if resolved_id else False
        svc_step(
            "user",
            "GET patients/me",
            resolved_ok and matches,
            f"HTTP {r.status_code} resolved_id={resolved_id} matches={matches}",
        )
    except Exception as e:
        svc_step("user", "GET patients/me", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['user']}/api/v1/patients/{patient_id}", headers=auth, timeout=5)
        svc_step("user", "GET patient", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("user", "GET patient", False, str(e)[:120])

    try:
        r = requests.put(
            f"{SERVICES['user']}/api/v1/patients/{patient_id}",
            headers=auth,
            json={"first_name": "VerifyUpd", "phone": "+1-555-0100"},
            timeout=5,
        )
        svc_step("user", "PUT patient", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("user", "PUT patient", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['user']}/api/v1/patients/{patient_id}/push_token",
            headers=auth,
            json={
                "token": verification_push_token or "verification-registration-only",
                "platform": os.environ.get("VERIFY_PUSH_PLATFORM", "android"),
            },
            timeout=5,
        )
        svc_step("user", "POST push_token", r.status_code in (200, 201), f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("user", "POST push_token", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['user']}/api/v1/patients/{patient_id}/risk", headers=auth, timeout=5)
        svc_step("user", "GET patient risk", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    except Exception as e:
        svc_step("user", "GET patient risk", False, str(e)[:120])

    # ---- symptom-service ----
    hr("symptom-service")
    # Submit three clearly synthetic symptom reports to demonstrate full risk workflow
    synthetic_reports = [
        {
            "symptoms": ["fever", "cough"],
            "temperature": 37.8,
            "heart_rate": 85,
            "spo2": 98.0,
            "systolic_bp": 118,
            "diastolic_bp": 78,
            "note": "mild synthetic case",
        },
        {
            "symptoms": ["fever", "cough", "fatigue", "shortness_of_breath"],
            "temperature": 38.9,
            "heart_rate": 102,
            "spo2": 94.0,
            "systolic_bp": 125,
            "diastolic_bp": 82,
            "note": "moderate synthetic case",
        },
        {
            "symptoms": ["fever", "cough", "fatigue", "shortness_of_breath", "chest_pain"],
            "temperature": 39.4,
            "heart_rate": 115,
            "spo2": 91.0,
            "systolic_bp": 135,
            "diastolic_bp": 88,
            "note": "severe synthetic case",
        },
    ]

    for i, report_data in enumerate(synthetic_reports, start=1):
        try:
            payload = {
                "patient_id": patient_id,
                "region_id": EPI_REGION,
                **report_data,
            }
            r = requests.post(
                f"{SERVICES['symptom']}/api/v1/symptoms",
                headers=auth,
                json=payload,
                timeout=10,
            )
            ok = r.status_code in (200, 201)
            response_risk_score = None
            response_risk_tier = None
            response_report_count = None
            if ok:
                try:
                    body = r.json()
                    response_risk_score = body.get("risk_score")
                    response_risk_tier = body.get("risk_tier")
                    response_report_count = body.get("report_count")
                except Exception:
                    pass
            detail = f"HTTP {r.status_code} {report_data['note']}"
            if i == len(synthetic_reports) and ok:
                # Validate numeric risk on final report (POST symptoms returns risk_tier and report_count)
                score_finite = isinstance(response_risk_score, (int, float)) and math.isfinite(response_risk_score)
                tier_valid = isinstance(response_risk_tier, str) and response_risk_tier in VALID_RISK_TIERS
                count_valid = isinstance(response_report_count, int) and response_report_count == len(synthetic_reports)
                ok = ok and score_finite and tier_valid and count_valid
                detail = (
                    f"HTTP {r.status_code} score={response_risk_score} tier={response_risk_tier} count={response_report_count}"
                )
            svc_step("symptom", f"POST symptoms#{i}", ok, detail)
        except Exception as e:
            svc_step("symptom", f"POST symptoms#{i}", False, str(e)[:120])

    try:
        r = requests.get(f"{GATEWAY_URL}/api/v1/patients/{patient_id}/history", headers=auth, timeout=5)
        ok = r.status_code == 200
        history_items = []
        if ok:
            try:
                history_items = r.json()
                # Fresh patient: expect exactly the three synthetic reports.
                ok = isinstance(history_items, list) and len(history_items) == len(synthetic_reports)
            except Exception:
                ok = False
        svc_step(
            "symptom",
            "GET history through gateway",
            ok,
            f"HTTP {r.status_code} count={len(history_items)} expected={len(synthetic_reports)}",
        )
    except Exception as e:
        svc_step("symptom", "GET history through gateway", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['symptom']}/v1/risk/deterioration",
            headers=auth,
            json={
                "patient_id": patient_id,
                "age": 36,
                "days_since_onset": 3,
                "fever_duration_h": 24,
                "fever_max_24h": 38.8,
                "heart_rate_current": 95,
                "hr_slope_48h": 0.1,
                "local_hosp_rate": 0.05,
                "n_comorbidities": 0,
                "regional_Rt": 1.2,
                "risk_score_acceleration": 0.05,
                "risk_score_current": 0.6,
                "spo2_current": 96.0,
                "spo2_min_24h": 94.0,
                "spo2_slope_48h": -0.1,
            },
            timeout=10,
        )
        svc_step("symptom", "POST risk/deterioration", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        svc_step("symptom", "POST risk/deterioration", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['symptom']}/v1/risk/score/{patient_id}", headers=auth, timeout=10)
        ok = r.status_code == 200
        risk_score = None
        tier = None
        if ok:
            try:
                body = r.json()
                risk_score = body.get("risk_score")
                tier = body.get("tier")
                # Verify risk_score is finite numeric (not NaN, not Inf) using math.isfinite
                score_valid = isinstance(risk_score, (int, float)) and math.isfinite(risk_score)
                tier_valid = isinstance(tier, str) and tier in VALID_RISK_TIERS
                ok = score_valid and tier_valid
            except Exception:
                ok = False
        svc_step(
            "symptom",
            "GET risk/score",
            ok,
            f"HTTP {r.status_code} score={risk_score} tier={tier}",
        )
    except Exception as e:
        svc_step("symptom", "GET risk/score", False, str(e)[:120])

    # ---- prescription-service ----
    hr("prescription-service")
    rx_id: str | None = None
    try:
        r = requests.post(
            f"{SERVICES['prescription']}/api/v1/prescriptions",
            headers=auth,
            json={
                "patient_id": patient_id,
                "drug_name": "Acetaminophen",
                "dosage": "500 mg",
                "frequency": "every 6 hours",
                "start_date": "2026-08-20",
                "end_date": "2026-08-30",
                "ndc_code": "50580-506-02",
                "rxnorm_id": "161",
                "notes": "verify-harness rx",
            },
            timeout=10,
        )
        ok = r.status_code in (200, 201)
        if ok:
            rx_id = r.json().get("id")
        svc_step("prescription", "POST prescription", ok, f"HTTP {r.status_code} rx_id={rx_id} {r.text[:140]}")
    except Exception as e:
        svc_step("prescription", "POST prescription", False, str(e)[:120])

    if rx_id:
        try:
            r = requests.get(f"{SERVICES['prescription']}/api/v1/prescriptions/{rx_id}", headers=auth, timeout=5)
            svc_step("prescription", "GET prescription", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            svc_step("prescription", "GET prescription", False, str(e)[:120])
        try:
            r = requests.put(
                f"{SERVICES['prescription']}/api/v1/prescriptions/{rx_id}/status",
                headers=auth,
                json={"status": "completed"},
                timeout=5,
            )
            svc_step("prescription", "PUT prescription status", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
        except Exception as e:
            svc_step("prescription", "PUT prescription status", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['prescription']}/api/v1/patients/{patient_id}/prescriptions", headers=auth, timeout=5)
        ok = r.status_code == 200
        items = r.json() if ok else []
        svc_step(
            "prescription",
            "GET patient prescriptions",
            ok,
            f"HTTP {r.status_code} count={len(items) if isinstance(items, list) else 'n/a'}",
        )
    except Exception as e:
        svc_step("prescription", "GET patient prescriptions", False, str(e)[:120])

    if include_external:
        try:
            r = requests.post(
                f"{SERVICES['prescription']}/api/v1/medications/scan",
                headers=auth,
                json={"ocr_text": "Acetaminophen 500 mg tablet", "patient_id": patient_id},
                timeout=15,
            )
            svc_step("prescription", "POST medications/scan", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
        except Exception as e:
            svc_step("prescription", "POST medications/scan", False, str(e)[:120])
    else:
        skipped_checks.append(
            "External medication lookup (POST /api/v1/medications/scan): requires --include-external-lookups flag and FDA/RxNorm API access"
        )
        print("  [SKIP] Prescription medication scan (external lookup disabled, local CRUD verified)")

    # ---- notification-service ----
    hr("notification-service")
    notif_id: str | None = None
    try:
        r = requests.post(
            f"{SERVICES['notification']}/api/v1/notifications",
            headers=auth,
            json={
                "patient_id": patient_id,
                "type": "risk_alert",
                "title": "High Risk Detected",
                "body": "Your risk score has increased.",
                "priority": "high",
            },
            timeout=5,
        )
        ok = r.status_code in (200, 201)
        if ok:
            notif_id = r.json().get("id")
        svc_step("notification", "POST notification", ok, f"HTTP {r.status_code} id={notif_id} {r.text[:140]}")
    except Exception as e:
        svc_step("notification", "POST notification", False, str(e)[:120])

    if notif_id:
        try:
            r = requests.patch(
                f"{SERVICES['notification']}/api/v1/notifications/{notif_id}",
                headers=auth,
                json={"read": True},
                timeout=5,
            )
            svc_step("notification", "PATCH notification", r.status_code == 200, f"HTTP {r.status_code} {r.text[:140]}")
        except Exception as e:
            svc_step("notification", "PATCH notification", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['notification']}/api/v1/notifications", headers=auth, timeout=5)
        ok = r.status_code == 200
        items = r.json() if ok else []
        svc_step(
            "notification",
            "GET notifications",
            ok,
            f"HTTP {r.status_code} count={len(items) if isinstance(items, list) else 'n/a'}",
        )
    except Exception as e:
        svc_step("notification", "GET notifications", False, str(e)[:120])

    if verification_push_token:
        try:
            r = requests.post(
                f"{SERVICES['notification']}/api/v1/notifications/send",
                headers=auth,
                json={
                    "patient_id": patient_id,
                    "title": "Alert",
                    "body": "Risk score increased.",
                    "data": {"risk_score": 0.8},
                },
                timeout=10,
            )
            svc_step(
                "notification", "POST notifications/send", r.status_code in (200, 202), f"HTTP {r.status_code} {r.text[:140]}"
            )
        except Exception as e:
            svc_step("notification", "POST notifications/send", False, str(e)[:120])
    else:
        skipped_checks.append(
            "External push delivery: set VERIFY_PUSH_TOKEN to a real device token and configure the matching provider."
        )
        print(f"  [SKIP] {skipped_checks[-1]}")

    try:
        with requests.get(
            f"{SERVICES['notification']}/api/v1/physicians/{keycloak_id}/alerts/stream",
            headers=auth,
            stream=True,
            timeout=2,
        ) as r:
            ok = r.status_code == 200
            svc_step("notification", "GET alerts/stream", ok, f"HTTP {r.status_code}")
    except requests.exceptions.ReadTimeout:
        svc_step("notification", "GET alerts/stream", True, "stream alive (timeout as expected)")
    except Exception as e:
        svc_step("notification", "GET alerts/stream", False, str(e)[:120])

    # ---- epi-engine ----
    hr("epi-engine")

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/params", headers=auth, timeout=5)
        svc_step("epi", "GET region params", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("epi", "GET region params", False, str(e)[:120])

    try:
        r = requests.get(
            f"{SERVICES['epi']}/api/v1/regions/{region}/forecast", headers=auth, params={"horizon_days": 7}, timeout=30
        )
        forecast = r.json() if r.status_code == 200 else {}
        trajectory = forecast.get("trajectory", {})
        forecast_valid = (
            forecast.get("region_id") == region
            and forecast.get("horizon_days") == 7
            and trajectory.get("t", [None])[-1] == 7
            and all(
                len(trajectory.get(compartment, [])) == len(trajectory.get("t", []))
                and all(
                    isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in trajectory[compartment]
                )
                for compartment in ("S", "E", "IA", "IM", "IS", "H", "ICU", "R", "D")
            )
        )
        svc_step("epi", "GET region forecast", forecast_valid, f"HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        svc_step("epi", "GET region forecast", False, str(e)[:120])

    try:
        deadline = time.monotonic() + 20
        while True:
            r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/state", headers=auth, timeout=5)
            if r.status_code != 404 or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        state = r.json() if r.status_code == 200 else {}
        observation_processed = (
            state.get("region_id") == region
            and state.get("filter_type") in ("ekf", "pf")
            and state.get("timestamp") is not None
            and all(
                isinstance(state.get("state", {}).get(compartment), (int, float))
                and math.isfinite(state["state"][compartment])
                and state["state"][compartment] >= 0
                for compartment in ("S", "E", "IA", "IM", "IS", "H", "ICU", "R", "D")
            )
        )
        svc_step("epi", "Kafka observation → filter state", observation_processed, f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "GET region state", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/Rt", headers=auth, timeout=5)
        reproduction_estimate = r.json() if r.status_code == 200 else {}
        reproduction_valid = (
            reproduction_estimate.get("region_id") == region
            and isinstance(reproduction_estimate.get("latest_Rt"), (int, float))
            and math.isfinite(reproduction_estimate["latest_Rt"])
            and reproduction_estimate["latest_Rt"] >= 0
            and all(
                lower <= mean <= upper and all(math.isfinite(value) for value in (lower, mean, upper))
                for lower, mean, upper in zip(
                    reproduction_estimate.get("Rt_lower", []),
                    reproduction_estimate.get("Rt_mean", []),
                    reproduction_estimate.get("Rt_upper", []),
                    strict=True,
                )
            )
        )
        svc_step("epi", "GET region Rt", reproduction_valid, f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "GET region Rt", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['epi']}/api/v1/control/weights/{region}",
            headers=auth,
            json={
                "C1": 1.0,
                "C2": 1.0,
                "C3": 1.0,
                "C4": 1.0,
                "W_u1": 0.5,
                "W_u2": 0.5,
                "W_u3": 0.5,
                "ethical_framework": "utilitarian",
                "notes": "verify-harness",
            },
            timeout=60,
        )
        svc_step("epi", "POST control weights", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "POST control weights", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/control/weights/{region}", headers=auth, timeout=5)
        svc_step("epi", "GET control weights", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("epi", "GET control weights", False, str(e)[:120])

    try:
        r = requests.get(
            f"{SERVICES['epi']}/api/v1/control/recommendations", headers=auth, params={"region_id": region}, timeout=20
        )
        svc_step("epi", "GET control recommendations", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        svc_step("epi", "GET control recommendations", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['epi']}/api/v1/mobility/upload",
            headers=auth,
            params={"region_id": region},
            files={"file": ("mobility.csv", b"from_patch_id,to_patch_id,fraction\nregion-verify,region-b,0.3\n", "text/csv")},
            timeout=10,
        )
        svc_step("epi", "POST mobility/upload", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "POST mobility/upload", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/map/hotspots", headers=auth, params={"region_id": region}, timeout=10)
        svc_step("epi", "GET map/hotspots", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        svc_step("epi", "GET map/hotspots", False, str(e)[:120])

    # ---- privacy-service ----
    hr("privacy-service")
    try:
        r = requests.post(
            f"{SERVICES['privacy']}/internal/dp/gaussian",
            headers=auth,
            json={"value": 100.0, "epsilon": 1.0, "delta": 1e-5, "sensitivity": 1.0},
            timeout=10,
        )
        svc_step("privacy", "POST dp/gaussian", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    except Exception as e:
        svc_step("privacy", "POST dp/gaussian", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['privacy']}/internal/dp/publish",
            headers=auth,
            json={"region_id": region, "stat_type": "count", "value": 42, "epsilon": 1.0},
            timeout=10,
        )
        svc_step("privacy", "POST dp/publish", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("privacy", "POST dp/publish", False, str(e)[:120])

    try:
        response = requests.get(f"{SERVICES['privacy']}/api/v1/fl/status", headers=auth, timeout=5)
        response.raise_for_status()
        round_status = response.json()
        round_id = round_status["current_round_id"]
        minimum_clients = round_status["min_clients"]
        svc_step("privacy", "GET fl/status", True, f"active round={round_id}")
    except Exception as error:
        svc_step("privacy", "GET fl/status", False, str(error)[:120])
        return 1

    for i in range(minimum_clients):
        try:
            client_email, client_password, _, client_keycloak_id = reg_user(f"fl_{suffix}_{i}")
            client_token = get_user_token(client_email, client_password)
            r = requests.post(
                f"{SERVICES['privacy']}/api/v1/fl/upload_gradient",
                headers=auth_headers(client_token),
                json={
                    "user_id": client_keycloak_id,
                    "round_id": round_id,
                    "gradient": [0.01, -0.02, 0.03, 0.04, -0.05, 0.06, -0.07, 0.08, -0.09, 0.10],
                    "n_samples": 100,
                },
                timeout=10,
            )
            svc_step("privacy", f"POST fl/upload_gradient#{i + 1}", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            svc_step("privacy", f"POST fl/upload_gradient#{i + 1}", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['privacy']}/api/v1/fl/trigger_aggregation",
            headers=auth,
            timeout=10,
        )
        svc_step("privacy", "POST fl/trigger_aggregation", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("privacy", "POST fl/trigger_aggregation", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['privacy']}/api/v1/fl/model/{round_id}", headers=auth, timeout=5)
        svc_step("privacy", "GET fl/model", r.status_code == 200, f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("privacy", "GET fl/model", False, str(e)[:120])

    # ---- Kafka cross-service ----
    hr("Kafka cross-service")
    try:
        import socket

        kafka_host = os.environ.get("KAFKA_HOST", "127.0.0.1")
        kafka_port = int(os.environ.get("KAFKA_PORT", "9092"))
        with socket.create_connection((kafka_host, kafka_port), 3):
            step("kafka-tcp", True, f"{kafka_host}:{kafka_port} reachable")
    except Exception as e:
        step("kafka-tcp", False, str(e)[:120])

    # ---- metrics ----
    hr("Metrics endpoints")
    for svc, base in SERVICES.items():
        try:
            r = requests.get(f"{base}/metrics", timeout=3)
            has_lines = "process_" in r.text or "python_" in r.text
            svc_step(svc, "/metrics", r.status_code == 200 and has_lines, f"HTTP {r.status_code} bytes={len(r.text)}")
        except Exception as e:
            svc_step(svc, "/metrics", False, str(e)[:120])

    # ---- summary ----
    hr("SUMMARY")
    total = len(results)
    failed = [r for r in results if not r[2]]
    passed = total - len(failed)
    print(f"Passed: {passed}/{total}")
    print(f"Skipped: {len(skipped_checks)}")
    if failed:
        print("\nFailures:")
        for svc, name, _, msg in failed:
            print(f"  - {svc}/{name}: {msg}")
        return 1
    print("\nALL EXERCISED CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
