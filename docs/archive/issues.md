# CyberEpi — Discovered Issues

Live-reproduced during manual testing on 2026-08-25. Each entry: what was tested, observed evidence, fix plan.

## ISS-01 — DP `consume()` race returns 500 on first concurrent requests

**Surface**: `services/privacy-service/src/api/routers/dp.py` → `services/privacy-service/src/dp/persistent_budget.py:65` → `consume()`.

**Repro (live, Redis up, Postgres up)**:
- Register a brand-new user → get JWT.
- Fire 50 concurrent POST `/internal/dp/publish` requests with `epsilon=0.1`.
- Sequential baseline (same user, 30 reqs eps=0.5): `Counter({200: 20, 403: 10})` — clean.
- Concurrent 50 reqs eps=0.1: `Counter({200: 46, 500: 4})` — 4 of 50 fail with `Internal Server Error`.

**Root cause**: `consume()` does `SELECT ... WHERE user_id = ? FOR UPDATE`. If no row exists yet (new user), it `session.add(DPBudget(...))` and `flush()`. With N concurrent calls for the same new user, N sessions all see no row, all try to INSERT a row with the same PK (`user_id` is the PK on `dp_budgets`). The first one to commit wins; the rest get `UniqueViolation` → unhandled exception → 500.

**Fix**: replace the `SELECT → INSERT-if-None` pattern with an idempotent upsert of the row under a single statement, then take the row-level lock:
1. Execute `INSERT INTO dp_budgets (user_id, consumed, max_budget, updated_at, reset_count) VALUES (:uid, 0, :max, now(), 0) ON CONFLICT (user_id) DO NOTHING`.
2. Then `SELECT ... WHERE user_id = :uid FOR UPDATE` to lock the now-guaranteed-to-exist row.
3. Read current consumed, decide whether new_total <= max_budget, otherwise `return False`.
4. Else update `budget.consumed = new_consumed`, append `DPQuery`, commit.

This guarantees exactly one row per user, no UNIQUE violations, and the row-level lock still serializes budget updates correctly.

**Verification**: re-run the 50-concurrent repro; expect `Counter({200: 50})` for a fresh user with full budget.

---

## ISS-02 — Federated learning workflow is broken (round lifecycle)

**Surface**: `services/privacy-service/src/api/routers/fl.py` and `services/privacy-service/src/federated/aggregator.py`.

**Repro (live)**:
- `POST /api/v1/fl/trigger_aggregation` → returns 200 with a model (round 1).
- After trigger, `POST /api/v1/fl/upload_gradient` with `round_id=1` → `400 "Round not active"` (the hardcoded check passes, but `aggregator.start_new_round()` was called by `trigger_aggregation`, so the round is already closed).
- `POST` with `round_id=99` → `400 "Round not active"` (hardcoded `round_id != 1`).
- `GET /api/v1/fl/model/99` → `404 "No model available for this round"` (hardcoded `round_id != 1`).
- Real clients can NEVER submit a gradient, because the round closes the moment `trigger_aggregation` runs.

**Root cause** — three independent bugs:
1. **Hardcoded round**: `upload_gradient` rejects any `round_id != 1`; `get_model` rejects any `round_id != 1`. Only round 1 exists, but the aggregator also closes it immediately.
2. **Round closes on trigger**: `trigger_aggregation` calls `aggregator.start_new_round()` right after aggregating, so the just-completed round is wiped; subsequent uploads to that round hit `has_submitted()` against an empty set (false) but find `current_round_gradients == []` and no model was produced for round_id != 1 anyway.
3. **In-memory state with no persistence**: the aggregator keeps `current_round_gradients` and `global_model` only in RAM. After a service restart, all round state is lost. `fl_model_versions` / `fl_rounds` DB tables exist but are never written to.

**Fix**:
- Add `current_round_id: int = 1` to the aggregator; `start_new_round(new_id)` increments it and clears gradients/clients.
- `upload_gradient` accepts the request iff `req.round_id == aggregator.current_round_id`. (Hardcoded `1` → use the tracked value.)
- `get_model(round_id)` returns the model for any past round that has a stored result. Keep an in-memory `dict[int, np.ndarray]` of `completed_models` indexed by round_id. Persist each completed round to `fl_model_versions` (round_id PK + serialized weights).
- `trigger_aggregation` does NOT close the round itself. It validates `K >= min_clients`, runs FedAvg, stores the result under `aggregator.current_round_id`, then `start_new_round()` increments to `current_round_id + 1` and clears gradients. Subsequent uploads to the just-completed round_id get "Round not active" (correct), and uploads to the new round_id are accepted (correct).
- Enforce `min_clients` properly: `trigger_aggregation` returns `400` (with a structured message) if `K < min_clients`, instead of raising `ValueError` (currently the existing code masks this — only 0-client case gets a 400).

**Verification**:
- Start fresh (restart service so in-memory state is empty, round 1 active).
- 3 clients upload gradients to round 1.
- Trigger aggregation → 200 with `new_update`; `fl_model_versions` has round 1.
- 4th upload to round 1 → 400 (closed).
- Upload to round 2 → 202 (accepted).
- GET `/fl/model/1` → 200 with weights.
- GET `/fl/model/2` → 404 (no aggregation yet).

---

## ISS-03 — privacy-service crash on startup blocks clean restart

**Surface**: `services/privacy-service/src/main.py:41` → `command.upgrade(alembic_cfg, "head")`.

**Repro (live)**: tail of `logs/privacy-service.log` from a prior restart attempt shows:
```
File "/home/avinash/Projects/CyberEpi/services/privacy-service/src/main.py", line 41, in lifespan
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
...
alembic.util.exc.CommandError: No 'script_location' key found in configuration.
ERROR:    Application startup failed. Exiting.
```

**Root cause**: the Alembic `Config` object built in `main.py` does not set `script_location`, so `command.upgrade` aborts the entire service before any routes are served. The current running instance started OK (apparently the migration already ran on a prior invocation), but any restart hits this error.

**Fix**: locate the alembic `env.py` / `alembic.ini`, set `cfg.set_main_option("script_location", "<absolute path to alembic dir>")` (or `script_location = privacy_service_migrations:alembic` if package-based). Verify by restarting the service and watching for clean startup with `INFO: Application startup complete`.

**Verification**: `kill <pid>` and restart privacy-service; logs show successful startup, no Alembic error.

---

## ISS-04 — Symptom POST returns null risk despite epi-engine computing risk in DB

**Surface**: `services/symptom-service/src/api/routers/symptoms.py:140-160`.

**Repro (live, E2E)**:
- Register a fresh patient, get token.
- POST symptom with `severity=9`, `symptom=fever`.
- Response: `risk_score: null, risk_tier: null, report_count: 1`.
- DB check on `vitals_ts` after 5s: row present with `risk_score = 0.082, risk_tier = low`.

**Root cause**: the symptom POST path returns a synthetic response built from request fields without re-reading the freshly computed risk. The epi-engine Kafka consumer DOES compute and write risk to `vitals_ts`, but by the time the symptom POST returns, that consumer hasn't necessarily processed the event yet (Kafka round-trip). When the patient later GETs `/api/v1/patients/{id}/risk`, it correctly reads from `vitals_ts` and returns `0.082 / low`.

**Severity**: misleading UX (the response says "no risk" even after computing one); NOT a data integrity issue. Risk data flows correctly via the GET endpoint.

**Fix options** (pick one):
- **(a)** Poll `vitals_ts` for up to ~2s after the Kafka publish; return latest known risk if it appears. Cleaner UX, but couples symptom-service to epi-engine timing.
- **(b)** Drop the synthetic `risk_score/risk_tier` fields from the POST response. Keep `report_count` only; force clients to fetch `/risk` separately. Less misleading, simpler, but a breaking API change.
- **(c)** Document the field as "may be null until risk is computed asynchronously" in OpenAPI; clients fetch `/risk` for latest. Minimal change.

Recommend **(c)** for short-term, **(b)** in v2.

---

## ISS-05 — Alembic env.py missing from privacy-service migrations

**Surface**: `services/privacy-service/alembic/` directory.

**Repro**: `ls services/privacy-service/alembic/` shows no `env.py` / `versions/` (only the pyc cache). The `alembic_cfg` in `main.py:41` is built but cannot find scripts.

**Root cause**: migrations were never authored for privacy-service. The DB tables exist because they were created out-of-band (raw SQL or `Base.metadata.create_all`), so the live service works. But any `alembic upgrade head` aborts.

**Fix**: scaffold the missing migration tree (`env.py`, `versions/0001_initial.py` with all `dp_budgets` / `dp_queries` / `fl_rounds` / `fl_model_versions` etc. tables), point `cfg.set_main_option("script_location", "<dir>")` at it, and verify a clean upgrade runs without error.

---

## ISS-06 — Symptom-service "risk score" null after POST; push-token route also broken

**Surface**: `services/user-service/src/api/routers/patients.py:282-310` (`/api/v1/patients/{patient_id}/push-token`).

**Repro (live)**:
- Authenticated as `alice`, `POST /api/v1/patients/{patient_id}/push-token` with `{token: "fcm-test-token-12345", platform: "fcm"}` → `405 Method Not Allowed`.
- The route only exists for `POST /api/v1/prescriptions` (no `/push-token`).

**Root cause**: the patient-app tests assume `/push-token` exists; the actual route is `/api/v1/prescriptions` (prescription-service) or absent. Symptom-service tests confirm 422 on missing field — but the test passed.

**Fix**: confirm where push tokens should be registered. If in user-service, add `POST /api/v1/patients/{patient_id}/push-token`. If in notification-service, fix the patient-app API client URL.

---

## ISS-07 — Service health sometimes masks failed dependencies

**Surface**: `services/*/src/main.py` lifespan → `/health` endpoint.

**Repro (live)**: brought down Redis briefly, then brought it back. `health` endpoint kept returning `200 {redis: healthy}` for ~5s after Redis actually died. This is acceptable (cached status) but not documented.

**Severity**: low; would cause silent failures if a service is genuinely unhealthy.

**Fix**: add a `cache_ttl` config to health-check ping, default 2s; document the lag.

---

## ISS-08 — Alembic / SQLAlchemy model missing timestamp default on `dp_budgets`

**Surface**: `services/privacy-service/src/db/models.py:18-30`.

**Repro**: code review; not runtime-tested. `DPBudget.updated_at` has `onupdate=lambda: datetime.now(UTC)` but no `default=`. First INSERT without explicitly setting `updated_at` triggers the server-side default to be the model's class-level default — which IS set, so this works. Documented as `low` priority for clarity.

---

## ISS-09 — Register route is idempotent in DB but returns 201 for duplicates

**Surface**: `services/user-service/src/api/routers/patients.py:119-210` `register_patient()`.

**Repro (live)**:
- Register `race@example.com` once → 201.
- Register same email 10x in parallel → all 10 return 201, DB has 1 row (good — Keycloak returns 409 first, falls back to existing row).
- However, the test result above shows 10/10 returned 201, which means each was either (a) hitting Keycloak's "user exists" path and reusing, or (b) the lookup returns the existing row.

**Severity**: spec ambiguous. REST convention is 201 only on first creation; subsequent should be 200 or 409. Current behavior (201 every time) violates REST.

**Fix**: track a `_created` boolean; return 201 if newly created, 200 (with same body) if Keycloak already had the user and we linked it. Don't return 409 — the UX is "the account is now usable, here's its info."

---

## ISS-10 — Patient-app tests don't cover auth race / token expiry

**Surface**: `apps/patient-app/src/__tests__/test_auth_store.ts`.

**Repro (live)**: ran `npx jest` on patient-app, all 47 tests pass. But there is no test for:
- Concurrent login from same account
- Token expiry mid-session
- Network failure during auth

**Fix**: add tests in `__tests__/test_auth_store.ts` covering these scenarios.

---

## ISS-11 — `Keycloak scripts/seed-data.py` does not record user IDs

**Surface**: `scripts/seed-data.py`.

**Repro**: seeded users exist but `seed-data.py` does not return or persist user UUIDs to a known file, so any subsequent test must look up by email.

**Fix**: have `seed-data.py` write a `seed-state.json` containing `{email: {id, password, roles}}` for downstream consumers.

---

---

# Current disposition (2026-10-18)

The original observations above are retained. This review distinguishes current
implementation defects from explanations that no longer match the code.

| Issue | Current disposition | Implementation and observed evidence |
|---|---|---|
| ISS-01 | User's atomic budget fix preserved and verified | `persistent_budget.py` creates a row with `ON CONFLICT DO NOTHING` before locking it. Fifty simultaneous first-user requests all returned 200; PostgreSQL recorded consumption of 5.0. Exhaustion returned 403. |
| ISS-02 | Fixed and verified | Completed FL updates persist in `fl_rounds`; startup restores the next round ID. Duplicate clients returned 409, simultaneous triggers returned 200/400, and closed-round uploads returned 400. Restart preserved the exact completed update and accepted the next round. Incomplete uploads remain process-local; one worker/container is required. |
| ISS-03 | Fixed and verified | Privacy startup resolves Alembic paths from the service directory. `alembic/env.py` uses the asyncpg engine instead of requiring an absent synchronous driver. Clean-container startup applied migrations successfully. |
| ISS-04 | Partially valid; client defect fixed | Symptom risk is calculated synchronously; fewer than three reports legitimately return null. The app's API client declared an envelope but returned an unwrapped body. It now returns `{data, status}`. Actual app modules submitted three reports through the gateway and received numeric risk. |
| ISS-05 | Original missing-tree claim is not current | The privacy migration tree exists and includes the completed-round migration. It was exercised against an empty database, not inferred from file existence. |
| ISS-06 | Client contract fixed and verified | The existing user-service endpoint expects `{token, platform}`, not `{push_token, platform}`. The app now sends that contract and requests a native FCM/APNs token rather than an incompatible Expo relay token. Actual module registration succeeded; external device delivery is not verified. |
| ISS-07 | Active health defect fixed and verified | `libs/shared/src/shared/health.py` actively fetches Kafka metadata rather than trusting cached brokers, and bounds database connection acquisition and queries. Stopping Redis, Kafka, and PostgreSQL produced health 503; restarting each restored 200. |
| ISS-08 | Default corrected and verified | `DPBudget.updated_at` has a Python insertion default as well as its database default. Actual concurrent inserts stored non-null timestamps. |
| ISS-09 | Secure conflict behavior retained and verified | Duplicate public registration returns 409 without an existing patient's identifiers. Returning another user's data would not be safe idempotency. Public registration accepts only patient roles; staff roles require administrative provisioning. |
| ISS-10 | Implementation and regression coverage completed | PKCE uses a valid 128-character verifier and base64url S256 challenge. Refresh is single-flight in AuthService; API 401s retry and permanent failure clears tokens and authenticated state. `/api/v1/patients/me` resolves JWT subject to the distinct local patient UUID and precedes the dynamic UUID route. Real-module HTTP smoke passed authorization-code login, identity resolution, concurrent refresh/retry, and failure logout. TypeScript and all 87 Jest tests passed (2026-10-18). |
| ISS-11 | Original identity-output claim does not match this script | `scripts/seed-data.py` seeds three regional `EpiParams` records, not users. It neither creates Keycloak identities nor prints account passwords. A user-ID JSON export is therefore not a missing part of this script's current contract. |

## Verification and limits

- **Prior implementation report (retained for comparison, not current audit
  evidence)**: 52/52 HTTP checks and negative checks were reported as passing;
  external push delivery was reported as skipped.
- **Current independent audit (2026-10-18)**: 442 distinct Python tests passed
  (428 default + 10 additional Epi integration + four backtest regressions);
  Jest: 87 passed; TypeScript passed. The current offline HTTP harness passed
  54/54 checks with two explicit provider skips; negative checks passed.
- PostgreSQL outage/recovery was exercised. Health returned 503 during outage.
  After restart, an initial patient login returned 500; a subsequent login and
  existing patient lookup succeeded. JDBC background validation is configured
  every 30 seconds, not a guarantee of immediate or maximum-30-second recovery.
- Real app services were loaded from their TypeScript source for HTTP smoke;
  native storage/device/browser boundaries were shimmed, not the API/auth code.
- Runtime verification also exposed and fixed missing spatial-state migration
  columns and a deterioration-prediction crash in the existing heuristic mode.
  PostgreSQL migration smoke preserved historical population totals.
- No physical-device UI or external FCM/APNs delivery was exercised. Those
  require a supported device/runtime, real provider credentials, and a device
  token. Stored notifications and successful registration are not delivery proof.
- Verification used disposable project resources only. No commit, push, or
  production deployment was performed.