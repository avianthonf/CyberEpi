# CyberEpi Single-host Deployment

## Supported target and scope

The supported deployment is **all six existing services on one Linux host**,
using Podman Compose or Docker Compose. It does not require paid hosting, a
container registry, Kubernetes, or restoration of the optional monitoring
images. `docker-compose.prod.yml` is the authoritative containerized topology.
Despite its historical filename, this is a local, loopback-bound deployment,
not an Internet-hardened production environment.

The chosen constraints are an existing machine, no additional hosting cost,
and no known hard image-size, RAM, or storage cap. Keep the current multi-stage
Python slim builds; optimize further only against measured requirements.

## Runtime inventory

| Component | Responsibility | Required dependencies |
| --- | --- | --- |
| user-service | Patient registration/profile and device tokens | PostgreSQL, Redis, Keycloak |
| symptom-service | Symptom ingestion and individual risk calculation | PostgreSQL, Redis, Kafka, Keycloak |
| prescription-service | Prescriptions and medication lookup | PostgreSQL, Redis, Keycloak; external FDA/RxNorm APIs for lookups |
| notification-service | Notification records, event consumption, streaming and push delivery | PostgreSQL, Redis, Kafka, Keycloak; device-provider credentials for real push delivery |
| epi-engine | Regional filters, forecasts, Rt and control | PostgreSQL, Redis, Kafka, Keycloak |
| privacy-service | Differential privacy budgets and federated aggregation | PostgreSQL, Redis, Keycloak |
| TimescaleDB/PostgreSQL | Application data and Keycloak database | Persistent volume |
| Redis | Cache, state and notification pub/sub | Persistent volume |
| Zookeeper | Kafka cluster coordination and metadata | Persistent volume |
| Kafka | Symptom and epidemiology events | Zookeeper, broker storage |
| Keycloak | Realm, users, roles and signed access tokens | PostgreSQL |
| Kong | Common API entry point and existing routing/rate limits | Backend services, Redis |

`libs/shared` supplies common auth, database, health and connection helpers;
`libs/seir-core` supplies the scientific model. The patient app remains a
separate Expo/native client. Backtesting can run independently of the stack.

Kafka is not unused infrastructure: symptom events feed notification handling
and the epi-engine's regional observation processing. Keycloak is also not
optional for authenticated workflows. Firebase/APNs delivery needs real
provider credentials; a successful HTTP request without those credentials is
not proof that a device received a push notification.

Provider credential paths must point to files **inside** the notification
container. To enable push, add a read-only credential-file bind mount in a
local Compose override and set `FIREBASE_CREDENTIALS_PATH` or `APNS_KEY_PATH`
to its container path. Environment variables alone do not copy host files
into the image. Keep the files and override out of version control.

## Prepare and start

On Arch Linux, Podman needs a Compose provider in addition to the engine:

```bash
sudo pacman -S --needed podman podman-compose
```

Run from the repository root:

```bash
bash scripts/prepare-deploy.sh
podman-compose --env-file .env.production -p cyberepi-singlehost -f docker-compose.prod.yml build
podman-compose --env-file .env.production -p cyberepi-singlehost -f docker-compose.prod.yml up -d --force-recreate
```

With Docker, substitute `docker compose` for `podman-compose`. Preparation is
local only: it must not publish images, copy cloud templates into the root,
or replace an existing credentials file. Keep `.env.production` private and
out of version control. The root `.dockerignore` excludes local environment
files, virtual environments, dependency trees, data and test artifacts from
image build contexts. All service Dockerfiles use the **repository root** as
their build context, not their service directory.

Use a new Compose project name when moving from older configurations. Named
volumes belong to that project. Do not attach a legacy database volume to the
new stack without inspecting and backing up its schema first: old raw SQL
bootstrap files and service-owned migrations did not describe identical
schemas. Existing volumes are not automatically migrated or deleted by this
workflow.

Database initialization provides extensions and the Keycloak database;
services own their application schema initialization. Migration assets must
be included in the service images. Startup ordering must complete shared
schema owners before dependent services start.

Default local service ports are 8001–8006, Kong is 8000, and Keycloak is 8080.
Infrastructure and direct service ports are loopback-bound. Configure the
published-port environment variables in Compose if these are occupied.
Do not start the host-process development workflow on the same ports.
Kong's administrative interface is not published.

## Verify the running system

Use the repository virtual environment for the Python verification tools:

```bash
bash scripts/setup-venv.sh
.venv/bin/python scripts/smoke.py --retries 10 --timeout 5
```

`smoke.py` checks `/health` and `/metrics` for every service. Health probes
check Redis and the database, plus Kafka where the service uses its producer.
Dependency checks are bounded but run sequentially; the whole HTTP response
can take longer than a single probe timeout. Health does not certify external
push providers, scientific model quality, or every background task.

The following harnesses create users and application records. Run them
against a disposable test project, not a database whose contents must remain
unchanged:

```bash
# Export the locally generated credentials for the harness, not only Compose.
# Source only your own trusted, generated environment file.
set -a
. ./.env.production
set +a
.venv/bin/python scripts/verify_all.py
.venv/bin/python scripts/verify_negative.py
```

Set `KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` in the verification process
to the generated credentials. Do not paste credentials into shell history or
reports. The Compose environment file does not automatically export values
into a separately launched Python process.

For nondefault addresses, `smoke.py` and `verify_all.py` accept
`USER_SERVICE_URL`, `SYMPTOM_SERVICE_URL`, `PRESCRIPTION_SERVICE_URL`,
`NOTIFICATION_SERVICE_URL`, `EPI_ENGINE_URL`, and `PRIVACY_SERVICE_URL`.
`SERVICE_PORT_OFFSET` shifts all default direct-service ports. The API
harness also accepts `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KAFKA_HOST`, and
`KAFKA_PORT`. Negative checks import this same configuration.

The positive harness discovers the current FL round and uses distinct
registered clients rather than spoofing identities or submitting the same
client repeatedly. Regional parameters are initialized before sending
observations so the downstream filter has the data it requires.
The demonstrated workflow is registration and Keycloak authentication,
patient/profile resolution, symptom submission and risk scoring, Kafka-fed
regional filtering/Rt, forecasts and control, notification records, and
privacy-budget/FL-round operations. Medication lookup calls FDA/RxNorm only
when `--include-external-lookups` is explicitly supplied.

External push delivery is skipped unless `VERIFY_PUSH_TOKEN` contains a real
device token and the matching FCM/APNs provider is configured. Set
`VERIFY_PUSH_PLATFORM` to `android` or `ios` as appropriate. A successful token
registration or stored notification does not prove delivery to a device.

Inspect status and logs without printing the resolved Compose environment,
which contains credentials:

```bash
podman-compose --env-file .env.production -p cyberepi-singlehost -f docker-compose.prod.yml ps
podman-compose --env-file .env.production -p cyberepi-singlehost -f docker-compose.prod.yml logs --tail 100
```

## Persistence, shutdown and capacity

Stop the stack without deleting its data:

```bash
podman-compose --env-file .env.production -p cyberepi-singlehost -f docker-compose.prod.yml down
```

Do not add `--volumes`/`-v` unless intentionally deleting that project's data.
Do not run global image, container, or volume pruning as a deployment step.
Back up PostgreSQL and any required Redis/Kafka state before upgrades; test
restoration independently before relying on the backup.

For a clean demo **without deleting any existing data**, stop the current
project and select a new project name with fresh volumes:

```bash
make down
make up PROJECT=cyberepi-demo-2
make smoke
make down PROJECT=cyberepi-demo-2
```

Keep the same private environment file when returning to an existing project.
Starting the original project again reuses its retained data. Do not run both
projects on the same host ports simultaneously. This reset procedure consumes
additional disk space; it deliberately does not delete either project's data.

Measure the host rather than adding displayed image sizes together:

```bash
podman images
podman system df
podman stats --no-stream
```

Image sizes include shared layers. Disk usage also includes stopped
containers, old image layers, build intermediates and persistent data. An
image footprint is not a RAM requirement. Leave memory headroom for the
scientific workload and the patient app's development tooling.

### Measured local capacity (2026-10-18)

Measured on Linux 7.1.13 arm64, 16 GB RAM, 10 logical CPUs, Podman 6.1.3
and podman-compose 1.6.0. A new disposable project initialized empty volumes.
The final snapshot below follows synthetic workflows and a database restart;
it is not an untouched first-start or peak-load measurement.

| Measurement | Observed |
|---|---:|
| Distinct runtime images | 12 |
| Long-running containers | 12, plus one completed Kafka initializer |
| Deduplicated uncompressed runtime-image layers | 5.464 GiB (5,866,625,536 bytes; 93 unique layers) |
| Sum of displayed image sizes, counting shared layers repeatedly | 6.819 GiB |
| Healthy quiescent stack memory, three samples five seconds apart | 2.035, 2.036, 2.221 GiB |
| Initial project volume allocation / after synthetic workflows | 79.0 / 81.8 MiB |
| Container writable layers in final snapshot | 170.4 MiB |

The layer measurement matches the runtime images' `RootFS.Layers` digests
to Podman's overlay layer metadata and counts each layer's `diff-size` once.
It excludes unrelated images, build intermediates and filesystem metadata;
it is not an estimate of the entire Podman store. Other projects, historical
builds and caches are not part of this runtime requirement. No existing user
data was pruned. Reproduce the measurement with
`.venv/bin/python scripts/measure_stack.py --project YOUR_PROJECT`;
the JSON includes the machine, image IDs, component samples and commands.

Kong is configured with one Nginx worker; `podman top` confirmed exactly one.
Its memory was 121.5 MB in these samples. The earlier reported default-worker
before/after comparison was not independently repeated in this audit and is
not used as a measured optimization claim. The six application boundaries remain.

These idle observations are **not a peak-memory or minimum-machine guarantee**.
The tested 16 GB machine has room for the OS and development tools; use that
as the supported reference configuration. Planning at least 20 GiB free disk
is a conservative starting allowance, not a measured minimum: builds, Python
and Node dependencies, persistent observations, logs and accumulated caches
need space beyond the runtime layers. Smaller machines and sustained-load
capacity have not been validated. No arbitrary host resource cap is imposed.

Use one worker per service for consistent in-memory state (epi-engine Kafka consumer,
privacy-service FL aggregator) and to avoid metadata DDL races. The canonical deployment
runs one container per service; horizontally scaling these services requires coordination
not present in the current implementation. Do not use old Kubernetes/Helm replica defaults.
The current forecast mode runs inline; it does not require restoring a Celery worker.

## Patient app and local-development alternative

See the README and `apps/patient-app/.env.example` for the native client.
Point its API URL at the gateway, including the `/api/v1` prefix expected by
the client, and its auth URL at the same reachable Keycloak realm. On an
emulator or physical phone, `localhost` denotes that device, not this host.
Any non-loopback exposure requires an explicit network/security setup; do
not simply open database, broker, or admin ports.

### Native Android execution

This is an Expo SDK 51 / React Native 0.74 native application, not a browser
replacement. JavaScript bundles and component tests do not establish that
the app has launched on Android. Health, MMKV and other native modules need
a compatible native build; do not substitute Expo Go as execution evidence.

The installed React Native template specifies SDK/target 34, build-tools
34.0.0, NDK 26.1.10909125 and Gradle 8.6. Use Java 17. The native project has
not been generated in this checkout; Expo prebuild also needs its native
template and build dependencies. `--no-install` skips package installation,
but does not make an uncached prebuild or Gradle build an offline operation.

Current local prerequisites were inspected, not assumed:

| Requirement | Observed state |
|---|---|
| Android target | `adb devices -l` reports no attached device; no emulator/AVD or system image was found |
| Java | Java 17.0.20.1 is installed at `/usr/lib/jvm/java-17-openjdk`; the default Java is 27 |
| SDK tools | Platform-tools/ADB and command-line tools exist under `$HOME/Android/Sdk` |
| Compatible SDK and NDK | Only platform 37.0, build-tools 36/37 and NDK 30 were found; the versions required above are absent |
| Gradle/native template cache | Gradle 9.5/AGP 9.3 cache exists, not the required Gradle 8.6/AGP 8.2.1; the Expo native-template cache was not found |
| Host-tool execution | Installed `build-tools/36.0.0/aapt2` is x86-64 and fails to execute on this ARM64 host; FEX is installed but reports no configured root filesystem |

Installing SDK packages alone is therefore not a verified solution for this
host. An attached target plus either a compatible prebuilt APK or a runnable,
host-compatible Android build toolchain are prerequisites. Obtain authorization
before downloading SDKs, NDKs, native templates, Maven/Gradle dependencies or
system images. Do not upgrade Expo or change target versions merely to match
the currently installed SDK.

For an attached Android device, prefer USB ADB reverse forwarding over exposing
the backend on the LAN. Select the actual serial from `adb devices -l`:

```bash
export ANDROID_SERIAL=YOUR_DEVICE_SERIAL
adb -s "$ANDROID_SERIAL" reverse tcp:28000 tcp:28000
adb -s "$ANDROID_SERIAL" reverse tcp:28080 tcp:28080
adb -s "$ANDROID_SERIAL" reverse tcp:28081 tcp:28081
```

These ports match the isolated example stack. Change all three consistently
if using different published ports. With reverse forwarding, the app and its
system-browser login can use the same loopback Keycloak address/issuer:

```bash
cd apps/patient-app
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export EXPO_PUBLIC_API_URL=http://127.0.0.1:28000/api/v1
export EXPO_PUBLIC_KEYCLOAK_URL=http://127.0.0.1:28080
export EXPO_PUBLIC_KEYCLOAK_REALM=cyberepi
export EXPO_PUBLIC_KEYCLOAK_CLIENT_ID=cyberepi-patient-app
export EXPO_NO_TELEMETRY=1

# Run only after the target and compatible build dependencies are available.
# First generation/build can download dependencies and needs authorization.
./node_modules/.bin/expo run:android --device "$ANDROID_SERIAL" --port 28081
```

If a matching native build is already installed and only Metro is needed, use
`EXPO_OFFLINE=1 ./node_modules/.bin/expo start --localhost --port 28081`.
Do not combine `--offline` and `--localhost`: this Expo CLI treats them as
mutually exclusive flags. Keep the compatible `image-size` override.

Use synthetic data only. Verify registration, browser login/redirect, identity,
three symptom reports, history, session restoration, logout/account switching
and outage recovery on the actual target before marking those screens verified.
Do not place emergency calls or enable medical-provider/push calls while testing.
Camera/OCR, wearable permissions and provider delivery require separate evidence.
Stop Metro with Ctrl-C; stop only the selected Compose project without `-v`.
Reverse forwarding can be removed with
`adb -s "$ANDROID_SERIAL" reverse --remove tcp:28000` (and similarly for 28080/28081).

For development with host Uvicorn processes instead of service containers,
start infrastructure with `podman-compose -f infra/docker-compose.yml up -d`,
then use `bash scripts/services-up.sh` and `bash scripts/services-down.sh`.
This is a separate mode; the Makefile targets operate on the canonical full
Compose stack, not this host-process alternative.

## Historical plans and deployment assets

`deploy/free/`, `infra/k8s/`, and `infra/helm/` are historical deployment
assets, **not supported instructions for the chosen target**. Their presence
does not establish a requirement to restore services, publish images, use
multiple replicas, or deploy a monitoring stack. CI builds images but does
not publish or deploy them; that is intentional for a local deployment.

The former Render/Railway/Fly/Vercel and free-cluster instructions did not
establish a working full-stack deployment or current provider entitlements.
Do not rely on their old free-tier claims. A future cloud target needs a new
review of persistent storage, always-on event consumers, authentication,
networking, resource limits and actual provider pricing.

Dated verification reports and `docs/archive/kafka-fix-plan.md` record historical work.
`docs/archive/issues.md` retains the original observations alongside their current
disposition; not every suggested historical fix remains applicable.

## Before any public deployment

This local topology is not authorization to expose it publicly. Public use
requires TLS, explicit trusted origins and token audience/issuer policy,
Keycloak production configuration, secret rotation, backups, access controls,
and a review of medical/personal-data handling. Current token validation is
anchored to the configured realm's RS256 JWKS; audience validation is not
currently enabled. Do not enable development auth bypasses to make deployment
checks pass.
