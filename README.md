# CyberEpi: Epidemiological Forecasting & Response Platform

CyberEpi is a real-time epidemiological monitoring and response system. It combines compartmental SEIR modeling with partial-observability filters (EKF/particle filter), optimal control, and a microservices backend consumed by a React Native patient app.

This is a local research/engineering demonstration using **synthetic data**,
not medical advice or a clinically validated decision system. For a walkthrough,
architecture/trust map, evidence, limitations and defensible resume wording,
start with [PORTFOLIO.md](./PORTFOLIO.md).

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

## Forecast Validation (CDC FluSight targets)

The **standalone** `backtest/` SEIHDR + EAKF implementation has retained
retrospective CDC FluSight scoring artifacts (see
[BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md)). It is not the live epi-engine's
regional EKF/particle-filter/SEIR forecast path, and its scores do not validate
the API's scientific or clinical accuracy.

- Archived pooled relWIS **0.714** vs `FluSight-baseline`, across three seasons
  and 53 locations: **18,014 finite paired scores** from 18,020 comparison rows
  (six have missing truth). The independent audit recomputed the archived score
  arithmetic; it did not rerun the complete model or download surveillance data.
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
