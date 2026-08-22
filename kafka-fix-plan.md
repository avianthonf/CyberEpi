# Kafka Topic Fix Plan

## Root Cause Analysis
- **What**: Kafka topic mismatch: `symptom-service` produces to `patient.events`, `notification-service` consumes `alerts.push`. `symptom-reports` is missing.
- **Why**: Hardcoded topic names in both services.
- **Evidence**: `symptom-service/src/api/routers/symptoms.py` publishes to `patient.events`. `notification-service/src/main.py` consumes `alerts.push`.

## Impact Assessment
- **Services Blocked**: Notification of symptom reports to users.
- **Tests Blocked**: Kafka topology tests.
- **Criticality**: P2 (Breaks end-to-end notification flow).

## Fix Strategy
- **Approach**: Code change to unify on `symptom-reports` topic.
- **Files to Modify**: `services/symptom-service/src/api/routers/symptoms.py`, `services/notification-service/src/main.py`.
- **Commands to Run**: 
  - `podman exec cyberepi-kafka /usr/bin/kafka-topics --bootstrap-server localhost:9092 --create --topic symptom-reports --partitions 1 --replication-factor 1` (Already executed)
- **Configuration Changes**: N/A
- **Validation**: 
  - Produce a test message to `symptom-reports` topic.
  - Verify `notification-service` consumes the message from `symptom-reports`.
  - Check consumer lag is zero.

## Dependencies
- **Must Fix First**: N/A
- **Can Fix in Parallel With**: N/A
- **Blocks These Fixes**: N/A

## Rollback Plan
- **How to Undo**: Revert `symptoms.py` and `main.py` to previous topics, delete `symptom-reports` topic.
- **State Backup**: N/A

## Risk Assessment
- **Risk Level**: Low
- **Potential Side Effects**: Disruption of current (incorrect) flow if it were actually used.
- **Blast Radius**: `symptom-service` and `notification-service`.

## Estimated Effort
- **Time**: 15-20 minutes
- **Complexity**: Simple
