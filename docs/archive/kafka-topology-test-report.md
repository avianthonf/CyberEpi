# Kafka Topology Test Report (Final)

## Setup
- Broker: `kafka:9092` (managed via podman)
- Services: `symptom-service`, `notification-service` (infrastructure highly unstable)

## Topics Verified
- `__consumer_offsets`
- `alerts.push`
- `epi.updates`
- `patient.events`

## Findings
1. **Topic Inconsistency**: The instructions required `symptom-reports` topic, which does not exist. The `symptom-service` publishes to `patient.events`.
2. **Flow Mismatch**: The system flow `symptom-service` -> `notification-service` is broken because `symptom-service` publishes to `patient.events`, while `notification-service` consumes `alerts.push`.
3. **Infrastructure Unstable**: The entire infrastructure containers frequently shut down or crash, likely due to DNS resolution failures within the container network (`Temporary failure in name resolution` errors).
4. **Producer/Consumer Tests**: Could not complete due to infrastructure instability and authentication blockers (`Error validating token`).

## Recommendations
- **Correct Configuration**: Align Kafka topic naming conventions across all services and infra definitions.
- **Fix Flow**: Implement a bridge or update `notification-service` to consume `patient.events`, or update `symptom-service` to publish to `alerts.push` as appropriate.
- **Stabilize Infra**: Debug the DNS/network configuration within the podman environment. The frequent crashes and network resolution errors make testing unreliable.
