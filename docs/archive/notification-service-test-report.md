# Notification Service Test Report (Updated)

## Component Status
- **Status**: Operational
- **Health Endpoint**: `/health` returned healthy status.
- **Kafka Connectivity**: **FIXED**. Replication factor updated to 1; Kafka broker is fully functional.

## Data Seeding Results
- **Messages Published**: 10 test notifications published to `alerts.push` topic.
- **Result**: Successfully published via `kafka-console-producer`. Verified via `podman logs` that the service consumed the messages and attempted to process them (although they failed due to lack of tokens, the consumer logic was exercised).

## API/Functionality Test Results
- **Authorization**: Verified that endpoint `/api/v1/notifications/send` correctly enforces authorization (403 for patients, authorized for physicians).
- **Validation**: Input validation (missing fields, malformed UUIDs) is working correctly (422 responses).
- **Push Logic**: 
    - The delivery logic paths (`_send_fcm` and `_send_apns`) were successfully triggered after seeding a valid `PushToken` in the database.
    - As expected in this test environment, the external service calls fail because the required credentials (Firebase/APNs) are not configured. The service correctly logs these failures and returns a 200 response indicating the attempt was made (as the delivery logic does not block the entire operation).

## Issues Found
1. **Kafka Replication Factor**: Mismatch between replication factor and brokers (resolved).
2. **Database Constraint Issue**: Foreign key to non-existent `patients` table (resolved with `use_alter=True`).
3. **Kafka Hostname Resolution**: Resolved via container networking.
4. **Missing Credentials**: Firebase/APNs credentials are missing, causing delivery attempts to fail (expected behavior).

## Recommendations
1. **Migrations**: Move to proper Alembic migrations.
2. **Credentials**: Configure valid credentials in the production environment for Firebase/APNs.
3. **Delivery Error Handling**: Refine the `send_notification` logic to handle delivery failures more gracefully (e.g., return specific details in the response about which platforms failed to deliver, rather than just returning a generic success).
