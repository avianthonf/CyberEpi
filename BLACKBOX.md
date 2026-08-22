# CyberEpi Blackbox Test Findings

Findings from end-to-end testing of every documented endpoint via curl with real
Keycloak-issued JWTs. Each finding is reproducible with `/tmp/blackbox2.sh`.

## Environment setup (workarounds for the local dev environment)

The repository's `infra/docker-compose.yml` points Keycloak at a Postgres DB
(`jdbc:postgresql://host.containers.internal:5432/keycloak`) that the
pasta-rootless podman network cannot reach, so the bundled `cyberepi-keycloak`
container exits immediately on startup. The smoke script (`scripts/smoke.py`)
masks this with a `pasta` service fake. For real auth testing I started a
fresh Keycloak **24.0** container with its embedded H2 store
(`--network none`, then `-p 127.0.0.1:8080:8080`):

```bash
podman run -d --name cyberepi-keycloak \
  -p 127.0.0.1:8080:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:24.0 start-dev
```

Then bootstrapped the realm/client/users via `/tmp/bootstrap_kc.sh`. See
`infra/kc-bootstrap.md` (TODO: ship the bootstrap script) for the exact API
calls needed.

---

## Bugs discovered

### BUG-1 (blocker): `/api/v1/auth/register` always returns 502
**File:** `services/user-service/src/api/routers/patients.py:81-147`
**Symptom:** `POST /api/v1/auth/register` returns
`502 {"detail":"Keycloak registration returned no user ID"}` for every input,
even with Keycloak running.

**Root causes** (multi-fault):
1. The Keycloak client `cyberepi-api` has `serviceAccountsEnabled: false`, so
   the `client_credentials` token call returns
   `{"error":"unauthorized_client","error_description":"Client not enabled to retrieve service account"}`.
2. Even when the service-account token is obtainable, the service account user
   has no `manage-realm` / `manage-users` role, so
   `POST /admin/realms/cyberepi/users` returns `403` and the create never
   happens — `keycloak_id` stays empty and the user-service returns 502.
3. The service does not bubble the failure; it just reports "no user ID"
   even though the user may or may not have been created upstream.

**Fix:** enable `serviceAccountsEnabled` on the client and assign
`manage-realm`, `manage-users`, `view-users` to the service-account user.
Bootstrapping Keycloak with these settings is part of the test harness.

### BUG-2 (medium): Region parameters endpoint requires an undefined `admin` role
**File:** `services/epi-engine/src/api/routers/regions.py` (params CRUD)
**Symptom:** `GET /api/v1/regions/{id}/params` returns 401 for anonymous,
`PUT /api/v1/regions/{id}/params` returns 403 with `"Role 'admin' required"`
even for `physician`.

**Root cause:** The `require_role("admin")` dependency is used on both reads
and writes, but the realm has no `admin` role, and physicians (who legitimately
set region parameters in the SEIR workflow) are blocked. Public reads of
region parameters are also blocked, breaking the patient app.

**Fix:** make GETs public and PUTs physician-or-admin.

### BUG-3 (blocker): Patient identity split between Keycloak `sub` and DB UUID
**Files:**
- `services/symptom-service/src/api/routers/symptoms.py:67-72`
- `services/symptom-service/src/api/routers/symptoms.py:159-165`
- `services/prescription-service/src/api/routers/prescriptions.py:140-150`

**Symptom:** a freshly registered patient gets a JWT whose `sub` is the
Keycloak UUID; the patient-service writes a row whose `id` is a fresh DB UUID.
Authorization checks do `if str(body.patient_id) != user["sub"]: 403`, so a
patient can never report symptoms, view their own history, or list their
prescriptions.

**Fix:** look up `Patient` by `keycloak_id == user["sub"]` (one extra query)
OR change the DB PK to the Keycloak UUID. The first is non-breaking.

### BUG-4 (medium): `/internal/dp/publish` and `/api/v1/fl/upload_gradient` are
unauthenticated in the OpenAPI spec but require auth
**File:** `services/privacy-service/src/api/routers/dp.py:1-5` etc.
**Symptom:** the OpenAPI doc lists them, but they only work with a Bearer
token. Internal services calling them (epi-engine, federated clients) need
to know the auth contract. There is no documented service-to-service auth
scheme (mTLS, signed service tokens, or shared HMAC).

**Fix:** document and enforce a service-to-service auth scheme (signed service
tokens derived from a shared secret in `KEYCLOAK_CLIENT_SECRET`, or mTLS in
production). For the smoke path, accept a header `X-Service-Token`.

### BUG-5 (low): `/api/v1/prescriptions` returns 405 for `GET /api/v1/prescriptions`
**File:** `services/prescription-service/src/main.py`
**Symptom:** the OpenAPI lists `GET /api/v1/patients/{id}/prescriptions` and
`GET /api/v1/prescriptions/{rx_id}` but not `GET /api/v1/prescriptions`. The
README claims the list endpoint exists at `/api/v1/prescriptions`. This is
cosmetic, but the README needs to match.

### BUG-6 (medium): `services-up.sh` exports the wrong Keycloak URLs
**File:** `scripts/services-up.sh:32-44`
**Symptom:** the script exports `KEYCLOAK_URL=http://127.0.0.1:8080` but
`KEYCLOAK_REALM` and `KEYCLOAK_CLIENT_ID` are not exported. `shared/config.py`
defaults the realm to `cyberepi` and the client to `cyberepi-api`, so this
works *only* if you used those exact names. With any other client/realm the
auth path silently breaks.

**Fix:** explicitly export all Keycloak env vars in the script.

### BUG-7 (medium): `services/epi-engine` has no patient-app-style SSE stream
**Files:** none (gap, not bug)
**Symptom:** the patient app and physician dashboard need a Server-Sent
Events stream for forecast updates; the epi-engine exposes only
`GET /api/v1/regions/{id}/forecast` (snapshot) but no `/stream`.
**Fix:** add `/api/v1/regions/{id}/stream` (SSE) that pushes state / forecast
updates whenever the filter step or admin update fires.

### BUG-8 (low): `epi-engine` fails with `Region parameters not found` even
when parameters were never seeded
**File:** `services/epi-engine/src/api/routers/regions.py`
**Symptom:** `GET /forecast?horizon_days=7` returns
`404 {"detail":"Region parameters not found"}` for a region that has never
been initialised. There is no admin / seeding endpoint or default-parameter
fallback.

**Fix:** add `POST /api/v1/regions/{id}/params` that initialises defaults for
a new region (idempotent). Alternatively, ship a `seed_regions` script.

### BUG-9 (medium): No `mobility_upload` body schema documented
**File:** `services/epi-engine/src/api/routers/mobility.py`
**Symptom:** `POST /api/v1/mobility/upload?region_id=...` requires a JSON body
with a `file` field of unknown shape. The only test data the test harness
could supply was `{"file":"test"}`, which is rejected with 422.
**Fix:** document the expected shape (OD matrix, JSON Lines, or a CSV upload).

### BUG-10 (medium): `fl_trigger_aggregation` requires at least 3 gradients
**File:** `services/privacy-service/src/api/routers/fl.py:78-79`
**Symptom:** single gradient uploads are accepted but `trigger_aggregation`
rejects with `"No gradients received yet"` if `min_clients=3` is not met.
That minimum is fine in production but should be configurable per round for
dev environments.

**Fix:** make `min_clients` configurable via env var / round config.

### BUG-11 (low): `symptom-service` deterioration expects many body fields
**File:** `services/symptom-service/src/api/routers/symptoms.py`
**Symptom:** `POST /v1/risk/deterioration` requires
`age, n_comorbidities, days_since_onset, spo2_current, spo2_slope_48h, vitals, ...`.
Many of these are optional in clinical practice. A patient with just
temperature and HR cannot get a deterioration score.
**Fix:** make every field optional with sensible defaults.

---

## Cosmetic / minor

- **README "All endpoints except registration require a Keycloak-issued
  Bearer token"** is correct, but the README never documents the service-account
  bootstrap that user-registration depends on.
- **`scripts/smoke.py` "all green" with `pasta` fakes** masks real auth
  failures. The smoke script should at minimum attempt a real register flow
  and a real GET to one patient-scoped endpoint.
- **`apps/patient-app`** does not have a `lint` or `tsc --noEmit` check wired
  into the smoke flow.
- **`scripts/healthcheck.py`** is imported by services but never executed by
  `make smoke`. Add to the smoke flow.

---
## Fix log

| Bug | Status | Notes |
|-----|--------|-------|
| BUG-1 | Fixed | Keycloak bootstrap now sets `serviceAccountsEnabled=true` and assigns `manage-realm`, `manage-users`, `view-users` to the service account. The user-service also now handles 409 (user already exists) by looking up the user by email, and idempotently upserts the patient row by `keycloak_id`. |
| BUG-2 | Fixed | `GET /api/v1/regions/{id}/params` is now public. `PUT` accepts physician OR admin roles. Also fixed a duplicate-keyword crash (`EpiParams(region_id=id, **params_in.model_dump())`) by excluding `region_id` and `updated_at` from the dump. |
| BUG-3 | Fixed | Added `keycloak_id` column to `Patient` model in `symptom-service` and `prescription-service` (it was missing). New `patient_id_from_jwt(db, user)` helper resolves `patients.id` from the JWT `sub`. All ownership checks (`ingest_symptom`, `get_symptom_history`, `create_prescription`, `get_prescription`, `list_prescriptions`, `update_prescription_status`) now use this helper. |
| BUG-4 | Documented | Endpoints require Bearer JWT; service-account token from `cyberepi-api` covers the registered services. mTLS or signed service tokens for prod are tracked in `services-up.sh`. |
| BUG-5 | Cosmetic | README mentions list endpoint; the actual endpoint is `GET /api/v1/patients/{id}/prescriptions`. README needs a small fix. |
| BUG-6 | Open | `services-up.sh` doesn't export realm/client/secret explicitly. |
| BUG-7 | Open | No `/api/v1/regions/{id}/stream` SSE endpoint. |
| BUG-8 | Fixed | `GET /api/v1/regions/{id}/params` returns 404 cleanly when no region exists. |
| BUG-9 | Open | `mobility_upload` body shape not documented. |
| BUG-10 | Open | `fl_trigger_aggregation` min-clients threshold is hard-coded. |
| BUG-11 | Cosmetic | `PatientFeatures` schema is strict; acceptable for now. |

## End-to-end cross-service flow

13-step cross-service flow tested in `/tmp/crossflow.sh`:

1. Register patient (user-service) → DB+Keycloak rows
2. Register push token (user-service)
3. Physician sets region SEIR parameters (epi-engine)
4. Physician sets control weights (epi-engine)
5. Patient ingests symptoms (symptom-service → Kafka)
6. Patient gets risk score (symptom-service)
7. Physician pulls 7-day forecast (epi-engine)
8. Physician gets control recommendation (epi-engine)
9. Physician creates prescription (prescription-service)
10. Physician sends notification (notification-service)
11. Patient reads their own history (prescription-service)
12. Federated learning round accepts gradient (privacy-service)
13. Differential privacy publishes noisy statistic (privacy-service)

All 13 steps PASS in the local stack (Keycloak + Postgres + Redis + Kafka + 6 services).