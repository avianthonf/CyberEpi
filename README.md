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
