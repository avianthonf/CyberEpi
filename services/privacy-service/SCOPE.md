# Privacy Service Scope Clarification

## Service Purpose
The privacy-service is focused on **ML Privacy** (Differential Privacy and Federated Learning), not PII-level GDPR compliance.

## Current Endpoints
- `POST /internal/dp/publish` - Add noise to a caller-supplied aggregate and account for its requested epsilon
- `POST /api/v1/fl/upload_gradient` - Upload federated learning gradients  
- `GET /api/v1/fl/model/{round_id}` - Retrieve the persisted aggregated update for a completed round
- `POST /api/v1/fl/trigger_aggregation` - Trigger FL aggregation

## What this does not establish

These endpoints demonstrate noise mechanisms, per-principal budget accounting,
and aggregation of submitted vectors. They do not establish end-to-end
differential privacy for patient records: `/internal/dp/publish` accepts a
caller-supplied value rather than executing a bounded query over private data,
and the assumed sensitivities require separate scientific justification.
The Gaussian utility endpoint does not consume a budget.

FL uploads are ten-dimensional vectors; the service does not train or deploy
a validated clinical model. Aggregation gives each accepted vector equal
weight; `n_samples` is not used for weighting. The upload budget charge (0.1)
and aggregation noise configuration (epsilon 0.5) are separate implementation
settings, not a proof of a composed privacy guarantee.

PII retention, consent, deletion, regulatory compliance, and production threat
modeling are not implemented by this service. Do not describe its presence as
GDPR compliance or as a guarantee that the entire platform is private.

## Deployment Constraints
- **Single worker required**: The FL aggregator maintains in-memory round state (`current_round_id`, `current_round_gradients`) that must not diverge across workers. The Dockerfile sets `--workers 1`. Completed rounds are persisted to the database and survive restarts, but active round state is in-memory only.
- **Database migrations**: Alembic migrations run automatically on startup. The service uses `alembic_version_privacy` to avoid conflicts with other services sharing the same database.

### Interrupted uploads: deliberate local demonstration constraint

No repository requirement establishes multi-worker aggregation or durable
incomplete uploads as part of the supported single-host demonstration.
Completed rounds are durable; an active round is not a durable upload queue.
One process and one container are therefore required, not merely recommended.

On a restart before aggregation, accepted gradients and the duplicate-client
set are lost. The active round ID is reconstructed from the last completed
round and can stay the same. **Already-consumed privacy budget remains in
PostgreSQL and is not refunded.** A client resubmitting its lost gradient is
accepted and charged again. Do not promise retry idempotency across restart.

The independent live audit exercised this exact sequence: completed update
unchanged after restart, incomplete gradient count reset to zero, retained
budget, and a newly charged resubmission. Complete a demonstration round before
restarting. A deployment needing resumable uploads or multiple workers would
require durable per-round uploads and coordinated idempotency, not an increased
worker count. That expansion is outside the current local portfolio scope.
