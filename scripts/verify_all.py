"""CyberEpi end-to-end verification harness.

Tests every service endpoint from first principles, using real Keycloak tokens
and live Kafka/Redis/Postgres backends. Exits 0 only when every step succeeds.
"""
from __future__ import annotations

import random
import string
import sys
import time

import requests

# ---------- config ----------
KC_URL = "http://127.0.0.1:8080"
REALM = "cyberepi"
ADMIN_TOKEN_URL = f"{KC_URL}/realms/master/protocol/openid-connect/token"
USER_TOKEN_URL = f"{KC_URL}/realms/{REALM}/protocol/openid-connect/token"
SERVICES = {
    "user": "http://127.0.0.1:8001",
    "symptom": "http://127.0.0.1:8002",
    "prescription": "http://127.0.0.1:8003",
    "notification": "http://127.0.0.1:8004",
    "epi": "http://127.0.0.1:8005",
    "privacy": "http://127.0.0.1:8006",
}
TEST_USER_PASSWORD = "password123!"
EPI_REGION = "region-verify"

results: list[tuple[str, str, bool, str]] = []


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
            "username": "admin",
            "password": "admin",
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


def main() -> int:
    print("CyberEpi verification harness starting...")

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

    # ---- user-service ----
    hr("user-service")
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
            json={"token": "fake-fcm-token-abc", "platform": "android"},
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
    try:
        r = requests.post(
            f"{SERVICES['symptom']}/api/v1/symptoms",
            headers=auth,
            json={
                "patient_id": patient_id,
                "symptoms": ["fever", "cough", "fatigue"],
                "temperature": 38.5,
                "heart_rate": 95,
                "spo2": 96.0,
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "region_id": EPI_REGION,
            },
            timeout=10,
        )
        ok = r.status_code in (200, 201)
        svc_step("symptom", "POST symptoms", ok, f"HTTP {r.status_code} body={r.text[:140]}")
    except Exception as e:
        svc_step("symptom", "POST symptoms", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['symptom']}/api/v1/patients/{patient_id}/history", headers=auth, timeout=5)
        ok = r.status_code == 200
        try:
            j = r.json()
            items = j.get("items") if isinstance(j, dict) else j
            count = len(items) if isinstance(items, list) else "n/a"
        except Exception:
            count = "?"
        svc_step("symptom", "GET history", ok, f"HTTP {r.status_code} count={count}")
    except Exception as e:
        svc_step("symptom", "GET history", False, str(e)[:120])

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
        svc_step("symptom", "GET risk/score", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
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
        svc_step("prescription", "GET patient prescriptions", ok, f"HTTP {r.status_code} count={len(items) if isinstance(items, list) else 'n/a'}")
    except Exception as e:
        svc_step("prescription", "GET patient prescriptions", False, str(e)[:120])

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
        svc_step("notification", "GET notifications", ok, f"HTTP {r.status_code} count={len(items) if isinstance(items, list) else 'n/a'}")
    except Exception as e:
        svc_step("notification", "GET notifications", False, str(e)[:120])

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
        svc_step("notification", "POST notifications/send", r.status_code in (200, 202), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("notification", "POST notifications/send", False, str(e)[:120])

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
    region = EPI_REGION
    try:
        r = requests.put(
            f"{SERVICES['epi']}/api/v1/regions/{region}/params",
            headers=auth,
            json={
                "region_id": region,
                "N_pop": 1000000,
                "beta": 0.4, "gamma": 0.1, "sigma": 0.2, "mu": 0.05,
                "alpha": 0.1, "delta": 0.05, "rho": 0.5,
                "gamma_A": 0.1, "gamma_M": 0.1, "gamma_S": 0.1, "gamma_H": 0.05, "gamma_ICU": 0.02,
                "h_rate": 0.05, "mu_icu": 0.05,
                "papp": 0.4, "fA": 0.3, "fM": 0.4, "fS": 0.3,
                "source": "manual_override",
            },
            timeout=30,
        )
        svc_step("epi", "PUT region params", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "PUT region params", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/params", headers=auth, timeout=5)
        svc_step("epi", "GET region params", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        svc_step("epi", "GET region params", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/forecast", headers=auth, params={"horizon": 14}, timeout=30)
        svc_step("epi", "GET region forecast", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        svc_step("epi", "GET region forecast", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/state", headers=auth, timeout=5)
        svc_step("epi", "GET region state", r.status_code == 200, f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "GET region state", False, str(e)[:120])

    try:
        r = requests.get(f"{SERVICES['epi']}/api/v1/regions/{region}/Rt", headers=auth, timeout=5)
        svc_step("epi", "GET region Rt", r.status_code == 200, f"HTTP {r.status_code} {r.text[:140]}")
    except Exception as e:
        svc_step("epi", "GET region Rt", False, str(e)[:120])

    try:
        r = requests.post(
            f"{SERVICES['epi']}/api/v1/control/weights/{region}",
            headers=auth,
            json={
                "C1": 1.0, "C2": 1.0, "C3": 1.0, "C4": 1.0,
                "W_u1": 0.5, "W_u2": 0.5, "W_u3": 0.5,
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
        r = requests.get(f"{SERVICES['epi']}/api/v1/control/recommendations", headers=auth, params={"region_id": region}, timeout=20)
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

    round_id = 1
    for i in range(3):
        try:
            r = requests.post(
                f"{SERVICES['privacy']}/api/v1/fl/upload_gradient",
                headers=auth,
                json={
                    "user_id": patient_id,
                    "round_id": round_id,
                    "gradient": [0.01, -0.02, 0.03, 0.04, -0.05, 0.06, -0.07, 0.08, -0.09, 0.10],
                    "n_samples": 100,
                },
                timeout=10,
            )
            svc_step("privacy", f"POST fl/upload_gradient#{i+1}", r.status_code in (200, 201), f"HTTP {r.status_code}")
        except Exception as e:
            svc_step("privacy", f"POST fl/upload_gradient#{i+1}", False, str(e)[:120])

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
        s = socket.create_connection(("127.0.0.1", 9092), 3)
        s.close()
        step("kafka-tcp", True, "9092 reachable")
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
    if failed:
        print("\nFailures:")
        for svc, name, _, msg in failed:
            print(f"  - {svc}/{name}: {msg}")
        return 1
    print("\nALL ENDPOINTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
