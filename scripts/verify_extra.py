"""Live coverage for endpoints NOT exercised by verify_all.py / verify_negative.py.

Covers:
  1. PUT  /api/v1/patients/{id}                    (self update + foreign 403)
  2. POST /api/v1/patients/{id}/push_token         (self ok)
  3. POST /api/v1/medications/scan                 (opt-in external lookup)
  4. PUT  /api/v1/prescriptions/{rx_id}/status     (physician transitions, patient 403, bad value 422)
  5. PATCH /api/v1/notifications/{id}              (owner marks read, foreign 403)
  6. POST /api/v1/notifications/send               (opt-in real device delivery)
  7. GET  /api/v1/physicians/{id}/alerts/stream    (SSE: publish -> receive)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time

import redis as sync_redis
import requests
from verify_all import SERVICES, get_admin_token, get_user_token, grant_physician_role, reg_user

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def jwt_sub(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


def main() -> None:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--include-external-lookups", action="store_true")
    arguments = argument_parser.parse_args()
    usr_svc, rx_svc, notif_svc = SERVICES["user"], SERVICES["prescription"], SERVICES["notification"]

    # ── users ──────────────────────────────────────────────
    name_a, pwd_a, pid_a, _kk_a = reg_user("xtra")
    grant_physician_role(name_a, get_admin_token())  # staff endpoints require physician role
    tok_a = get_user_token(name_a, pwd_a)
    ha = {"Authorization": f"Bearer {tok_a}"}
    name_b, pwd_b, _pid_b, _kk_b = reg_user("xtra")
    hb = {"Authorization": f"Bearer {get_user_token(name_b, pwd_b)}"}

    # 1. Patient self-update and foreign-update denial
    r = requests.put(f"{usr_svc}/api/v1/patients/{pid_a}", json={"phone": "+1-555-0100", "gender": "F"}, headers=ha, timeout=10)
    check("PUT patients/{id} self", r.status_code == 200, f"({r.status_code})")
    if r.status_code == 200:
        body = r.json()
        check("PUT patients/{id} persists", body.get("phone") == "+1-555-0100" and body.get("gender") == "F")
    r = requests.put(f"{usr_svc}/api/v1/patients/{pid_a}", json={"phone": "x"}, headers=hb, timeout=10)
    check("PUT patients/{id} foreign -> 403", r.status_code == 403, f"({r.status_code})")

    # 2. Push token registration (self)
    r = requests.post(
        f"{usr_svc}/api/v1/patients/{pid_a}/push_token",
        json={"token": "fcm-xtra-123", "platform": "android"},
        headers=ha,
        timeout=10,
    )
    check("POST push_token self", r.status_code in (200, 201), f"({r.status_code})")
    r = requests.post(
        f"{usr_svc}/api/v1/patients/{pid_a}/push_token", json={"token": "t", "platform": "carrier-pigeon"}, headers=ha, timeout=10
    )
    check("POST push_token bad platform -> 422", r.status_code == 422, f"({r.status_code})")

    # Medication lookup is external, even when the input is synthetic OCR text.
    if arguments.include_external_lookups:
        response = requests.post(
            f"{rx_svc}/api/v1/medications/scan",
            json={"ocr_text": "LIPITOR 20 MG TABLETS\nTake one tablet daily\nNDC 0071-0155-23", "patient_id": str(pid_a)},
            headers=ha,
            timeout=20,
        )
        check("POST medications/scan", response.status_code == 200, f"({response.status_code}) {response.text[:120]}")
    else:
        print("[SKIP] Medication lookup requires --include-external-lookups")

    # 4. Prescription status transitions
    rx_hdr = ha
    rx_body = {
        "patient_id": str(pid_a),
        "drug_name": "Lipitor",
        "ndc_code": "0071-0155-23",
        "dosage": "20mg",
        "frequency": "once daily",
        "start_date": "2026-08-22",
    }
    r = requests.post(f"{rx_svc}/api/v1/prescriptions", json=rx_body, headers=rx_hdr, timeout=10)
    check("POST prescriptions (setup)", r.status_code in (200, 201), f"({r.status_code}) {r.text[:120]}")
    rx_id = r.json().get("id") if r.status_code in (200, 201) else None
    if rx_id:
        r = requests.put(f"{rx_svc}/api/v1/prescriptions/{rx_id}/status", json={"status": "paused"}, headers=ha, timeout=10)
        check("PUT rx status active->paused", r.status_code == 200 and r.json().get("status") == "paused", f"({r.status_code})")
        r = requests.put(f"{rx_svc}/api/v1/prescriptions/{rx_id}/status", json={"status": "composted"}, headers=ha, timeout=10)
        check("PUT rx status invalid -> 422", r.status_code == 422, f"({r.status_code})")
        r = requests.put(f"{rx_svc}/api/v1/prescriptions/{rx_id}/status", json={"status": "active"}, headers=hb, timeout=10)
        check("PUT rx status as patient -> 403", r.status_code == 403, f"({r.status_code})")
        r = requests.get(f"{rx_svc}/api/v1/prescriptions/{rx_id}", headers=ha, timeout=10)
        check("GET rx reflects paused", r.status_code == 200 and r.json().get("status") == "paused", f"({r.status_code})")

    # 5 + 6. Notifications: create (as physician/staff path), read as owner, foreign 403, send
    r = requests.post(
        f"{notif_svc}/api/v1/notifications",
        json={
            "patient_id": str(pid_a),
            "title": "Lab ready",
            "body": "Your labs are in",
            "type": "reminder",
            "priority": "medium",
        },
        headers=ha,
        timeout=10,
    )
    check("POST notifications", r.status_code in (200, 201), f"({r.status_code}) {r.text[:100]}")
    nid = r.json().get("id") if r.status_code in (200, 201) else None
    if nid:
        r = requests.patch(f"{notif_svc}/api/v1/notifications/{nid}", json={"read": True}, headers=ha, timeout=10)
        check(
            "PATCH notifications/{id} owner mark-read",
            r.status_code == 200 and r.json().get("read") is True,
            f"({r.status_code})",
        )
        r = requests.patch(f"{notif_svc}/api/v1/notifications/{nid}", json={"read": False}, headers=hb, timeout=10)
        check("PATCH notifications/{id} foreign -> 403", r.status_code == 403, f"({r.status_code})")
        r = requests.get(f"{notif_svc}/api/v1/notifications", headers=ha, timeout=10)
        items = r.json() if r.status_code == 200 else []
        mine = [n for n in items if n.get("id") == nid]
        check("GET notifications shows read=true", bool(mine) and mine[0]["read"] is True, f"({len(items)} items)")

    verification_push_token = os.environ.get("VERIFY_PUSH_TOKEN")
    if verification_push_token:
        response = requests.post(
            f"{usr_svc}/api/v1/patients/{pid_a}/push_token",
            json={"token": verification_push_token, "platform": os.environ.get("VERIFY_PUSH_PLATFORM", "android")},
            headers=ha,
            timeout=10,
        )
        check("Register real delivery token", response.status_code in (200, 201), f"({response.status_code})")
        if response.status_code in (200, 201):
            response = requests.post(
                f"{notif_svc}/api/v1/notifications/send",
                json={"patient_id": str(pid_a), "title": "Push", "body": "Synthetic verification push"},
                headers=ha,
                timeout=15,
            )
            check("POST notifications/send", response.status_code == 200, f"({response.status_code}) {response.text[:120]}")
    else:
        print("[SKIP] Device delivery requires VERIFY_PUSH_TOKEN and provider credentials")

    # 7. SSE alert stream: subscribe, publish to redis, expect alert event
    physician_sub = jwt_sub(tok_a)  # after role grant, tok_a may be pre-grant; refresh
    tok_phys = get_user_token(name_a, pwd_a)
    physician_sub = jwt_sub(tok_phys)
    received: list[str] = []
    sse_error: list[str] = []

    def listen():
        try:
            with requests.get(
                f"{notif_svc}/api/v1/physicians/{physician_sub}/alerts/stream",
                headers={"Authorization": f"Bearer {tok_phys}"},
                stream=True,
                timeout=(5, 12),
            ) as resp:
                if resp.status_code != 200:
                    sse_error.append(f"status={resp.status_code}")
                    return
                for line in resp.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:") and "cyberepi-sse-probe" in line:
                        received.append(line)
                        return
        except requests.exceptions.ReadTimeout:
            pass
        except Exception as e:
            sse_error.append(str(e)[:100])

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(2.5)  # let SSE subscribe and heartbeat
    rc = sync_redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    rc.publish(f"alerts:{physician_sub}", json.dumps({"alert": "cyberepi-sse-probe", "severity": "high"}))
    t.join(timeout=8)
    check("SSE alerts/stream delivers published alert", bool(received), f"({len(received)} events; errors: {sse_error})")
    rc.close()

    # SSE authz: patient (no role) streaming another physician's channel
    r = requests.get(f"{notif_svc}/api/v1/physicians/{physician_sub}/alerts/stream", headers=hb, stream=True, timeout=(5, 8))
    check("SSE stream foreign -> 403", r.status_code == 403, f"({r.status_code})")

    print("\n=== SUMMARY ===")
    fails = [r for r in results if not r[1]]
    print(f"Passed: {len(results) - len(fails)}/{len(results)}")
    if fails:
        for name, _, d in fails:
            print(f"  FAIL: {name} {d}")
        sys.exit(1)
    print("ALL EXTRA COVERAGE PASSED")


if __name__ == "__main__":
    main()
