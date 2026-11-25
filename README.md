# CyberEpi: flu hospitalization forecasting

CyberEpi forecasts weekly influenza hospital admissions for the US and 52
jurisdictions with a mechanistic SEIHDR model and an ensemble Kalman filter,
in the format of the CDC FluSight challenge. The goal is a forecasting record
scored by someone else: weekly live forecasts for the 2026-27 season, judged
against data that did not exist when they were made. See [ROADMAP.md](./ROADMAP.md).

## Results so far (honest backtest)

Forecasts made only from data as the CDC published it each week; settings
frozen after tuning on 2023-24; scored once on 2024-25 and 2025-26
(53 locations, horizons 0–3, 11,660 scores). Full detail:
[BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md).

| Compared with | relWIS (below 1 = better) |
|---|---|
| CDC FluSight-baseline (persistence) | **0.697**, about 30% better |
| CDC FluSight-ensemble (all teams combined) | **1.046**, about level (3% better in 2024-25, 16% worse in 2025-26) |

Known weaknesses, stated up front:

- **Forecasts run low while epidemics decline.** The model's post-peak fall is
  too steep (3-week forecasts ~40% low in declining phases). An after-the-fact
  correction did not hold up on held-out seasons, so it is not applied; the
  fix belongs in the model ([backtest/calibrate.py](./backtest/calibrate.py)).
- **Intervals cover too little:** 90% intervals contain the truth ~74% of the time.
- **Still retrospective.** The live season is the real test.

An earlier headline (relWIS 0.714) used revised data and was tuned on the
seasons it reported; it is kept in [docs/archive/](./docs/archive/BACKTEST_RESULTS-2026-08.md)
with the reasons it was replaced.

## Live forecasting (2026-27)

`.github/workflows/weekly-forecast.yml` runs every Wednesday after the CDC
data release: it fetches the hub data, refuses to run on last week's data,
forecasts with the frozen settings in [backtest/model_config.json](./backtest/model_config.json),
and validates the files against the hub's rules. Submission to the CDC hub is
a manual step; see [SUBMITTING.md](./SUBMITTING.md).

```bash
pip install numpy pandas scipy jsonschema pyyaml
git clone --depth 1 https://github.com/cdcepi/FluSight-forecast-hub hub
python3 backtest/live.py --hub hub --out forecasts
```

Reproducing the backtest takes about 45 minutes on 4 CPUs; commands are in
[BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md#reproduce). Method details:
[backtest/METHODS.md](./backtest/METHODS.md).

Single-origin prospective mode: `python3 backtest/run_flusight.py
--reference-date YYYY-MM-DD` runs the filter through week R−7 and
forecasts a 4-week horizon exactly once — hub submission format via
`backtest/package_submission.py`, checked by `backtest/validate_submission.py`.

---

# Part 2: platform systems demo

Alongside the forecaster, this repository contains a local research and
engineering demonstration of a surveillance platform: six FastAPI services,
Kafka, Keycloak, Kong and an Expo patient app. It runs on **synthetic data
only** and is not medical advice or a clinically validated system. Its own
forecast path (epi-engine) is separate from the backtested forecaster above,
and the backtest scores do not validate it. Walkthrough, evidence and
limitations: [PORTFOLIO.md](./PORTFOLIO.md).

## Architecture

The [portfolio architecture map](./PORTFOLIO.md#what-this-project-demonstrates)
shows the six application services behind Kong, Keycloak authentication,
shared persistence, and the Kafka event path. Infrastructure containers are
additional to the six services.

- **`libs/seir-core`** — the epidemiological math: extended SEIR ODEs, solvers, Rt estimation. This is the scientific core and is unit-tested.
- **`libs/shared`** — shared service scaffolding: config, auth (Keycloak JWKS), DB sessions, security headers, health checks, Kafka/Redis connection helpers. All six services import it instead of re-implementing the same code.
- **`services/*`** — six FastAPI microservices. See [DEPLOYMENT.md](./DEPLOYMENT.md) for the full service inventory.
- **`apps/patient-app`** — the patient mobile app (Expo SDK 51, React Native).

## Prerequisites

- Python 3.12+ for host development and verification
- Podman with `podman-compose`, or Docker with Docker Compose
- Node.js 18+ and npm for the patient app
- Android Studio / Xcode and a compatible development build for native mobile features

On Arch Linux, `podman-docker` provides the `docker` command but does not
install a Compose provider. Install `podman-compose` separately if needed.

## Quick Start — Backend

The supported deployment target is a single Linux host running all six
services. No paid hosting, registry publication, Kubernetes cluster, or
monitoring stack is required.

Follow [DEPLOYMENT.md](./DEPLOYMENT.md) for credential preparation, the
authoritative `docker-compose.prod.yml` stack, safe verification, and
persistence. The older cloud templates are not complete deployment recipes.

The older host-process launchers are an alternative for backend development,
not the default deployment path. Do not run both workflows on the same ports.

Each service exposes:

- **`/health`** — dependency health checks (Redis, database, and Kafka where used). Returns 503 when a checked dependency is unhealthy; it is not a production availability guarantee.
- **`/docs`** — OpenAPI UI.
- **`/metrics`** — Prometheus metrics.

## Quick Start — Patient App

```bash
cd apps/patient-app
npm install
cp .env.example .env.local   # set API + Keycloak URLs
npx expo start
```

The app requires the running backend and a compatible native development build.
Android needs an installed emulator/AVD or device; iOS Simulator requires macOS
and Xcode. Starting Metro is not proof of native UI, camera or push behavior.
The audited Linux environment has no connected device or configured emulator;
the [local HTTP demonstration](./PORTFOLIO.md#prepare-start-demonstrate-stop)
does not require one.

Keep the `image-size` override on the compatible `^1.2.1` line: Metro 0.80 calls
its CommonJS export as a function, while version 2 exports a different API.
The live-run check reproduced the asset-transform failure with version 2 and
then successfully served full Android and iOS JavaScript bundles with 1.2.1.
This verifies bundling, not installation or execution on a physical device.
For an offline native packager, use `EXPO_OFFLINE=1 npx expo start --localhost`;
do not combine the mutually exclusive `--offline` and `--localhost` flags.
Browser support additionally needs the SDK-compatible `react-native-web` and
`react-dom` packages; these are not installed in the audited native setup.
See [native Android execution](DEPLOYMENT.md#native-android-execution) for
the inspected SDK/toolchain blockers, USB port forwarding, and launch commands.

## Running Tests

Run each Python package from its own directory so its `src` package and pytest
configuration are selected independently:

```bash
for package in libs/shared libs/seir-core \
  services/user-service services/symptom-service \
  services/prescription-service services/notification-service \
  services/epi-engine services/privacy-service; do
  (cd "$package" && ../../.venv/bin/python -m pytest -q) || exit
done

(cd apps/patient-app && npm run typecheck && npm test -- --runInBand)

# These create test users and records: use a disposable running stack.
.venv/bin/python scripts/verify_all.py
.venv/bin/python scripts/verify_negative.py
```

Observed results: **442 distinct Python tests passed**: 428 default package tests,
10 additional epi-engine integration tests, and four backtest regressions.
The patient app passed 87 Jest tests across six suites and TypeScript checking.
The disposable local stack passed **54/54 HTTP checks**, with two explicit skips
(FDA/RxNorm lookup and real push delivery); negative authorization checks passed.
The combined Epi run passed 65 tests: 55 default plus the 10 opt-in tests.
Of those 10, two use real PostgreSQL/Redis containers; eight mock infrastructure.
See [the independent audit record](PORTFOLIO.md#independent-audit-evidence-2026-10-18)
for commands, limitations, and the difference between mocked and live evidence.
The epi-engine's default pytest configuration excludes its opt-in integration
directory; the command below enables it.

To reproduce with rootless Podman and the development dependencies installed:

```bash
systemctl --user start podman.socket
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/podman/podman.sock"
(cd services/epi-engine && ../../.venv/bin/python -m pytest -o addopts= tests -q)
```

This uses Podman's Docker-compatible API, not a separate Docker daemon.
Testcontainers needs the PostgreSQL, Redis and Ryuk images available locally
or permission to pull them. Fixtures create isolated containers and clean
them up afterward. They override application startup to avoid migrations and
background consumers; the separate live Compose smoke covers those paths.

## CI

`.github/workflows/ci.yml` runs on push/PR:

- **test** — pytest for all 6 services against Postgres + Redis service containers
- **lint** — ruff over `services/` and `libs/`
- **security-scan** — Trivy FS + pip-audit
- **build-images** — docker build for all 6 services (main branch)

`.github/workflows/weekly-forecast.yml` produces the weekly FluSight forecast
(see [Live forecasting](#live-forecasting-2026-27)).

## Key API Contracts

| Endpoint | Service | Description |
|----------|---------|-------------|
| `POST /api/v1/auth/register` | user | Register a patient (Keycloak + patients table) |
| `GET /api/v1/patients/{id}/risk` | user | Latest risk score/tier from vitals |
| `POST /api/v1/symptoms` | symptom | Ingest symptom report → `{risk_score, risk_tier, report_count}` |
| `GET /api/v1/patients/{id}/history` | symptom | Symptom report history |
| `POST /api/v1/medications/scan` | prescription | `{ocr_text}` → drug/NDC/interaction lookup |
| `GET /api/v1/regions/{id}/forecast` | epi-engine | SEIR forecast (`horizon_days`, 1–42 days; default 14) |
| `POST /api/v1/control/weights/{region_id}` | epi-engine | Set optimal-control weights |

Protected endpoints require a Keycloak-issued Bearer token (RS256, verified against the realm JWKS). Registration and public regional parameter reads are explicit exceptions; authorization is enforced by each service.

## Contributing

- Services share code via `libs/shared` — add shared functionality there, not per-service copies.
- Backend changes need tests; frontend changes need `tsc --noEmit` clean.
- Run `ruff check services/ libs/` before pushing.

## Local Operations

The Make targets use the same containerized topology for startup, status,
logs and shutdown:

```bash
bash scripts/setup-venv.sh
make prepare   # first use only; never overwrites an existing environment
make up
make smoke
make status
make down      # retains this project's persistent data
```

Override `COMPOSE`, `PROJECT`, or `ENV_FILE` to select the engine, isolated
project, or credentials file. `make smoke` uses default host ports unless
service URLs or `SERVICE_PORT_OFFSET` are exported. See [DEPLOYMENT.md](./DEPLOYMENT.md)
for custom ports and security boundaries. The scientific backtest runs
independently of this stack.

## License & Citation

MIT — see [LICENSE](./LICENSE). If you use this software in research,
please cite it; see [CITATION.cff](./CITATION.cff).
