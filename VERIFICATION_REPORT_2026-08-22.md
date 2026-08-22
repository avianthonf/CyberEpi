# CyberEpi Stack Verification Report — 2026-08-22 (Run 2)

**Date**: 2026-08-22
**Method**: Full-stack re-verification from first principles after the resilience/hardening fixes
**Result**: PASS — all 6 services, all endpoints, all outage probes, all test suites, ruff clean, `tsc --noEmit` clean

---

## Stack Status

| Component | Port | Status |
|---|---|---|
| PostgreSQL (TimescaleDB) | 5432 | healthy |
| Redis | 6379 | healthy |
| Kafka (KRaft, 1 broker) | 9092 | healthy |
| Keycloak (`cyberepi` realm) | 8080 | healthy |
| user-service | 8001 | PASS (200, components `redis`/`database` healthy) |
| symptom-service | 8002 | PASS (+`kafka`) |
| prescription-service | 8003 | PASS |
| notification-service | 8004 | PASS |
| epi-engine | 8005 | PASS (+`kafka: 1 broker`) |
| privacy-service | 8006 | PASS |

`python scripts/smoke.py` → 6/6 PASS (health + metrics).

## Endpoint verification (live, real Keycloak RS256 JWTs)

- **Auth**: admin token, patient registration (201), user JWT issuance, realm role grant (physician) — all good; role claim visible in decoded token.
- **user-service :8001**: `POST /api/v1/auth/register` 201; `GET /api/v1/patients/{id}` 200 self-read; foreign-user read → **403** (cross-user authorization enforced); `POST /patients/{id}/push_token` OK; `GET /patients/{id}/risk` OK. Patient list endpoint intentionally removed (privacy hardening); list now only via `patients/me` (route-shifted — noted).
- **symptom-service :8002**: `POST /api/v1/symptoms` 201; `GET history`; `GET /v1/risk/score/{id}`; `POST /v1/risk/deterioration`. Kafka publish confirmed end-to-end (epi consumer log `epi_observation_batch`).
- **prescription-service :8003**: `POST /api/v1/prescriptions` 201; `GET /api/v1/prescriptions/{id}`; `POST /api/v1/medications/scan` → RxNorm lookup (`rxnorm_id 161`, acetaminophen); DDI endpoint returns the documented NLM deprecation notice (by design).
- **notification-service :8004**: `POST /api/v1/notifications` 200 (schema: `patient_id`, `title`, `body`, `type`, `priority`); `GET` list; mark-read, SSE alert stream verified previously.
- **epi-engine :8005**: `PUT/GET /api/v1/regions/{id}/params`; `GET forecast` (14-day); `GET state` (EKF filter state from Redis); `GET rt`; `PUT /api/v1/control/weights` triggers inline Forward-Backward Sweep (~15.6 s real optimization) then `GET /api/v1/control/recommendations` returns bounded controls. `converged: false` = solver exhausted `n_iter=1000` before `tol=1e-4`; output is bounded and valid — surfaced honestly, not a failure.
- **privacy-service :8006**: `POST /internal/dp/gaussian`; `POST /internal/dp/publish` (ε consumed, remaining tracked — observed 9.7 after one backtest-ε); FL round: `POST /api/v1/fl/upload_gradient` ×3 (min_clients=3 enforced — earlier triggers correctly refused), `POST trigger_aggregation` 200, `GET /api/v1/fl/model` OK.

## Outage / resilience probes (live)

| Probe | Result |
|---|---|
| Kafka down → `POST /symptoms` | **201 in milliseconds** — bounded publish (5 s `wait_for`) with `Failed to publish` log; no 40 s hang |
| Postgres down → `/health` all 6 | **503 fast (5–10 ms)**, payload `{"status": "unhealthy", ...}` after shared-lib fix; no app crash |
| Redis down → `/health` 8001 | 503 with component detail |
| Redis down → epi `GET /state` | 503 `"State store unavailable"`; clean recovery after Redis restart |

## Fixes landed in this session

1. `libs/shared/src/shared/health.py` — on component failure the handler raised 503 but never flipped `health_status["status"]` to `"unhealthy"`; now consistent (contract: HTTP 503 + `status: "unhealthy"`).
2. Ruff: 3× I001 auto-fixed; 5× SIM105 best-effort Redis cache sites converted to `contextlib.suppress` (`epi-engine` persistent_state, forecast router; `privacy-service` persistent_budget).
3. Test env hermeticity: `DATABASE_URL` defaulted in service `conftest.py` files (parse-only URL; engines connect lazily) — module-level `create_session_factory(settings)` no longer crashes collection.
4. Health-contract tests in user/prescription/notification updated: no-infra TestClient app now correctly asserts 503 + `status: unhealthy` + component detail (replaces stale 200 expectations).
5. `privacy-service/tests/integration/test_privacy_api.py` — lifespan runs Alembic migrations on TestClient enter; patched `src.main.command.upgrade` in the fixture so the suite is fully offline (Redis/budget tracker already mocked).

## Test suites (all green)

| Suite | Result |
|---|---|
| libs/shared | 30 passed |
| libs/seir-core | 15 passed |
| user-service | 10 passed |
| symptom-service | 16 passed |
| prescription-service | 9 passed |
| notification-service | 4 passed |
| epi-engine | 34 passed |
| privacy-service | 15 passed |
| **Total** | **133 passed, 0 failed** |

`ruff check services/ libs/` → All checks passed.
`apps/patient-app`: `tsc --noEmit` → clean (exit 0).

## Operational notes

- Service restart procedure matters: kill uvicorns by name (`pkill -f uvicorn`), restart via `scripts/services-up.sh`; Postgres must be up before launching services (services crash on boot without it).
- Shared lib is an editable install — edits to `libs/shared` require service restart to load.

## Result

Every service healthy, every endpoint exercised with real JWTs, all three outage degradations behave per contract, 133 unit/integration tests green, lint clean, app type-checks. Stack is operational.

---

# Brutal Final Assessment (Run 2 verdict)

Adversarial program completed end-to-end: recon (suites, lint, tsc) → exploit (authz probes, fuzz battery, service-outage probes, concurrency races) → findings adjudication → remediation → regression. All 17 planned items closed with live evidence.

## Exploit results (this run)

| Probe | Result |
|---|---|
| No-auth mutating call | 401 `Not authenticated` |
| Expired token (5-min JWT TTL) | 401 `Signature has expired` — enforced everywhere |
| Patient → PUT control weights | 403 `Role 'physician' or 'admin' required...` |
| Patient → cross-user symptom write / history | 403, exact-identity enforced |
| Fuzz battery (9 malformed payloads across 6 services: bad types, SQLi strings, 10k-char names, NaN, negatives, huge floats, path-traversal URL) | 9/9 → 4xx, zero 5xx; `../` normalized to 404 |
| Valid-UUID nonexistent patient symptom write | 403 (authz precedes FK resolution — correct precedence) |
| 8 concurrent symptom POSTs, same patient | 8/8 rows in `vitals_ts`, history = 8 — no lost updates |
| 5 concurrent FL `trigger_aggregation` | exactly 1 winner (200 `aggregated`), 4× 400 drained-buffer — no double aggregation |
| 8 concurrent DP publishes ε=1.0 | ledger decrements exactly once each: remaining set {8.7…1.7}, floor 9.7−8.0 — Redis Lua atomicity holds |
| 3 concurrent duplicate-email registrations | 3× 201, **same** patient id, single DB row — idempotent |
| Postgres down | all 6 `/health` → 503 `unhealthy` + detail, recovery clean |
| Redis down | epi `/state` 503 `State store unavailable`, health 503 |
| Kafka down | symptom POST 201 in ms, bounded publish failure logged, no hang |

## Residual risks (honest list)

1. **Control-weights PUT solves inline (~17 s).** `PUT /api/v1/control/weights/{region}` runs the full forward-backward sweep synchronously inside the request. Clients with `<17 s` timeouts see `000` while the server completes; retries stack duplicate solves (observed: two `recommendation_published` entries from timed-out client). Offload to the existing Celery `tasks.solve_optimal_control` and return 202, or raise client-face timeout guidance.
2. **FL aggregator is dev-grade.** Round is hard-capped at 1 (`round_id != 1` → 422; model served only for round 1), gradients live in-process (lost on restart), aggregated update returned in the response body but never published to Kafka. Fine for dev; not a production FL system.
3. **DP budget float noise.** `budget_remaining` returned `1.6999999999999993`. Atomicity is provable; presentation should quantize (round to 3 dp or use Decimal).
4. **Cost scale is weight-dominated.** Region-a solve cost = 3.25e9 vs seeded region-b ≈ 7.2e6 — unnormalized weights × cumulative incidence; `converged:false` is honest max-iter reporting (bounded u ∈ [0,1] at tol 1e-4), not a failure.
5. **Not exercised here:** real APNs/FCM delivery (push tokens persist; send path mocked), patient-app on an emulator (tsc clean only), k8s/helm manifests (dev compose used), TLS termination (dev is plaintext HTTP).

## Verdict

**Ship-shape for dev/CI. Production-ready subjects:** authn/authz, input validation, ledger/race integrity, failure-mode degradation are all contract-correct under live adversarial probing. **Not production-ready:** inline control solve (risk 1), FL round lifecycle (risk 2). Everything above is reproducible from this report plus `local/security-cleanup-report.md`.
