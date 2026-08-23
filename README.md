# CyberEpi: Epidemiological Forecasting & Response Platform

CyberEpi is a real-time epidemiological monitoring and response system. It combines compartmental SEIR modeling with partial-observability filters (EKF/particle filter), optimal control, and a microservices backend consumed by a React Native patient app.

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────────────┐
│  apps/patient-app       │     │  services/ (FastAPI)         │
│  Expo React Native      │────▶│  user-service     :8001      │
└─────────────────────────┘     │  symptom-service  :8002      │
                               │  prescription-service :8003  │
┌─────────────────────────┐     │  notification-service :8004  │
│  libs/                  │     │  epi-engine       :8005      │
│  seir-core (SEIR math)  │     │  privacy-service  :8006      │
│  shared (scaffolding)   │     └──────────┬───────────────────┘
└─────────────────────────┘                │
                               ┌──────────▼──────────┐
                               │  Infra (docker)     │
                               │  Postgres, Redis,   │
                               │  Kafka, Keycloak    │
                               └─────────────────────┘
```

- **`libs/seir-core`** — the epidemiological math: extended SEIR ODEs, solvers, Rt estimation. This is the scientific core and is unit-tested.
- **`libs/shared`** — shared service scaffolding: config, auth (Keycloak JWKS), DB sessions, security headers, health checks, Kafka/Redis connection helpers. All six services import it instead of re-implementing the same code.
- **`services/*`** — six FastAPI microservices. See [DEPLOYMENT.md](./DEPLOYMENT.md) for the full service inventory.
- **`apps/patient-app`** — the patient mobile app (Expo SDK 51, React Native).

## Prerequisites

- Python 3.12+
- Docker + Docker Compose (for infra: Postgres, Redis, Kafka, Keycloak)
- Node.js 18+ and npm (for the patient app)
- Android Studio / Xcode for mobile development

## Quick Start — Backend

```bash
# 1. Copy env template and edit values
cp .env.example .env.local

# 2. Start infrastructure (Postgres, Redis, Kafka, Keycloak)
cd infra
docker compose up -d
cd ..

# 3. Install core libraries
pip install -e ./libs/seir-core
pip install -e ./libs/shared

# 4. Run a service (example: symptom-service)
cd services/symptom-service
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8002
```

Each service exposes:

- **`/health`** — deep health check (Redis ping, DB `SELECT 1`, Kafka producer state). Returns 503 when any component is unhealthy.
- **`/docs`** — OpenAPI UI.
- **`/metrics`** — Prometheus metrics.

## Quick Start — Patient App

```bash
cd apps/patient-app
npm install
cp .env.example .env.local   # set API + Keycloak URLs
npx expo start
```

The app requires a running backend (Keycloak for auth, user/symptom/prescription services for data). Press `a` for Android emulator, `i` for iOS simulator.

## Running Tests

```bash
# All six services
for svc in user symptom prescription notification privacy epi-engine; do
  (cd services/$svc-service && pip install -e ".[dev]" && pytest -q)
done

# seir-core
(cd libs/seir-core && pytest -q)

# patient app (type-check + unit tests)
cd apps/patient-app && npx tsc --noEmit && npm test
```

## CI

`.github/workflows/ci.yml` runs on push/PR:

- **test** — pytest for all 6 services against Postgres + Redis service containers
- **lint** — ruff over `services/` and `libs/`
- **security-scan** — Trivy FS + pip-audit
- **build-images** — docker build for all 6 services (main branch)

## Forecast Validation (CDC FluSight targets)

The epi-engine's SEIHDR + EAKF forecaster is backtested against CDC
hospitalization targets (see [BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md)):

- **Pooled relWIS 0.714** vs the CDC persistence baseline (per-season
  0.66–0.86), across 3 FluSight seasons, 53 locations, 18,020 scored
  forecasts (h=0..3, FluSight scoring convention).
- Interval coverage: cov90 ≈ 0.85–0.91, cov50 ≈ 0.44–0.53 (near nominal
  at 0.5 and 0.9).
- Retrospective scoring by the in-repo harness; hub verification is the
  next step (`backtest/package_submission.py` emits hub-conformant
  quantile files + `model-metadata`).

One-command reproduction:

```bash
python3 backtest/run_flusight.py \
  --seasons 2023-24,2024-25,2025-26 \
  --locations US,01,02,04,05,06,08,09,10,11,12,13,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47,48,49,50,51,53,54,55,56,72 \
  --ncpus 8 --label EAKF-final
```

Single-origin prospective mode: `python3 backtest/run_flusight.py
--reference-date YYYY-MM-DD` runs the filter through week R−7 and
forecasts a 4-week horizon exactly once — hub submission format via
`backtest/package_submission.py`, checked by `backtest/validate_submission.py`.

## Key API Contracts

| Endpoint | Service | Description |
|----------|---------|-------------|
| `POST /api/v1/auth/register` | user | Register a patient (Keycloak + patients table) |
| `GET /api/v1/patients/{id}/risk` | user | Latest risk score/tier from vitals |
| `POST /api/v1/symptoms` | symptom | Ingest symptom report → `{risk_score, risk_tier, report_count}` |
| `GET /api/v1/patients/{id}/history` | symptom | Symptom report history |
| `POST /api/v1/medications/scan` | prescription | `{ocr_text}` → drug/NDC/interaction lookup |
| `GET /api/v1/regions/{id}/forecast` | epi-engine | SEIR forecast (7-21 day horizon) |
| `POST /api/v1/control/weights/{region_id}` | epi-engine | Set optimal-control weights |

All endpoints except registration require a Keycloak-issued Bearer token (RS256, verified against the realm JWKS).

## Contributing

- Services share code via `libs/shared` — add shared functionality there, not per-service copies.
- Backend changes need tests; frontend changes need `tsc --noEmit` clean.
- Run `ruff check services/ libs/` before pushing.
## Local Development

The repo ships a one-shot path (used by the verification reports):

```bash
bash scripts/setup-venv.sh   # one-time: .venv with all deps
make up                      # infra + services
make smoke                   # verify all services healthy
make status                  # container status
make down                    # stop and remove containers
```

All services share `libs/shared` and `libs/seir-core`.

## License & Citation

MIT — see [LICENSE](./LICENSE). If you use this software in research,
please cite it; see [CITATION.cff](./CITATION.cff).
