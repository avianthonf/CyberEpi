# Patient App Manual Verification Scenarios

## Prerequisites
- Backend stack running (user-service, notification-service, Keycloak)
- Android device with ADB or iOS device
- Valid FCM/APNs credentials configured in backend (for push delivery verification)

## 1. Push Token Registration After Authentication

**Scenario**: Device token registers with backend after successful login

**Steps**:
1. Launch patient app on device (not emulator without play services)
2. Complete login flow with valid credentials
3. Monitor network traffic or backend logs

**Expected**:
- POST `/api/v1/patients/{patient_id}/push_token` called after login
- Request body: `{"token": "ExponentPushToken[...]", "platform": "android|ios"}`
- Response: 201 Created
- Backend user-service database has push_token record for patient

**Verify**: 
```bash
# Check backend logs
podman logs cyberepi-singlehost-user-service-1 | grep "push_token"

# Query database
psql -U postgres -d cyberepi -c "SELECT patient_id, platform, substring(token, 1, 30) FROM push_tokens;"
```

## 2. Push Token Deregistration on Logout

**Scenario**: Device token removed from backend before credential clearing

**Steps**:
1. Login as Patient A
2. Verify token registered (scenario 1)
3. Tap logout button
4. Monitor network traffic

**Expected**:
- DELETE `/api/v1/patients/me/push_token` called before logout completes
- Request body: `{"token": "ExponentPushToken[...]", "platform": "android|ios"}`
- Response: 204 No Content
- Backend database no longer has push_token binding for Patient A
- Local credentials cleared after successful deregistration

**Verify**:
```bash
# Check deletion in backend logs
podman logs cyberepi-singlehost-user-service-1 | grep "DELETE.*push_token"

# Confirm token removed
psql -U postgres -d cyberepi -c "SELECT * FROM push_tokens WHERE patient_id = '{patient_a_uuid}';"
```

## 3. Cross-Account Push Token Transfer (Security Critical)

**Scenario**: Prevent Patient A notifications reaching Patient B on same device

**Steps**:
1. Login as Patient A on device
2. Note the device's push token from logs
3. Send test notification to Patient A (should arrive)
4. Logout Patient A (deregisters token)
5. Login as Patient B on same device
6. Patient B registration automatically transfers token ownership
7. Send notification to Patient A (should NOT arrive on device)
8. Send notification to Patient B (should arrive)

**Expected**:
- Patient A logout: DELETE removes token binding
- Patient B login: POST creates new binding with same token
- Backend enforces exclusive ownership via (patient_id, platform) composite key
- Only current token owner (Patient B) receives pushes to that token

**Verify**:
```bash
# Backend exclusive binding - only one patient per (token, platform)
psql -U postgres -d cyberepi -c "
SELECT patient_id, platform, substring(token, 1, 30), created_at 
FROM push_tokens 
WHERE token = 'ExponentPushToken[YOUR_TOKEN_HERE]'
ORDER BY created_at DESC;
"
# Should show only Patient B's binding

# Test notification delivery via backend
curl -X POST http://127.0.0.1:8001/api/v1/notifications/send \
  -H "Authorization: Bearer $PHYSICIAN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "{patient_a_uuid}",
    "title": "Test for A",
    "body": "Should not arrive after transfer"
  }'
```

## 4. Stale Logout Cleanup Race Protection

**Scenario**: Delayed DELETE cannot unbind new owner's token

**Steps**:
1. Login as Patient A (slow/unreliable network)
2. Initiate logout (DELETE queued, slow to send)
3. Before DELETE completes, login as Patient B on same device
4. Patient B token registration transfers ownership
5. Patient A's delayed DELETE arrives at backend

**Expected**:
- Patient B owns token after registration
- Patient A's stale DELETE includes exact token in body
- Backend returns 404 (token no longer bound to Patient A)
- Patient B's token binding remains intact
- No cross-patient notification leak

**Verify**:
```bash
# Backend token match enforcement
# DELETE only succeeds if (patient_id, platform, token) all match current binding
# Stale DELETE from Patient A with Patient B's token returns 404

# Check backend DELETE endpoint logs for 404 response
podman logs cyberepi-singlehost-user-service-1 | grep "404.*push_token"
```

## 5. Offline Queue + Session Isolation

**Scenario**: Symptom reports queued offline belong to correct patient after account switch

**Steps**:
1. Login as Patient A
2. Enable airplane mode
3. Submit 2 symptom reports (queued locally)
4. Logout Patient A (queued reports persist)
5. Login as Patient B
6. Patient B's session shows 0 queued reports
7. Disable airplane mode
8. Patient B submits 1 symptom report (syncs immediately)
9. Logout Patient B, login as Patient A
10. Patient A's 2 queued reports visible and sync when online

**Expected**:
- Symptom queue uses MMKV per-patient storage keys
- Session isolation prevents Patient B seeing Patient A's queue
- Push token transfer ensures notifications reach current patient only
- Risk scores calculated against correct patient's reports

**Verify**:
- Check symptom count badge on app symptoms tab
- Backend logs show correct patient_id in POSTed reports
- Risk scores update for correct patient

## 6. Notification Permission Grant

**Scenario**: Permission prompt appears, token registration respects user choice

**Steps**:
1. Fresh install or clear app data
2. Login for first time
3. System notification permission prompt appears
4. Deny permission
5. Check network - no POST /push_token
6. Grant permission later via system settings
7. Logout and login again

**Expected**:
- No token registration when permission denied
- Token registration succeeds after permission granted
- App functions normally without push permissions (local notifications still work)

**Verify**:
```bash
# No push_token record if permission denied
psql -U postgres -d cyberepi -c "SELECT COUNT(*) FROM push_tokens WHERE patient_id = '{patient_uuid}';"
```

## Runtime Prerequisites Check

Native Android execution requires:
- Android SDK 34, build-tools 34.0.0, NDK 26.1.10909125
- Java 17 (set JAVA_HOME=/usr/lib/jvm/java-17-openjdk)
- Physical device or emulator with Play Services for push tokens
- ADB reverse forwarding for loopback backend access:
  ```bash
  adb reverse tcp:8000 tcp:8000  # API gateway
  adb reverse tcp:8080 tcp:8080  # Keycloak
  ```

If no device available:
- Metro bundler smoke: `npm start` verifies JS bundle builds
- Typecheck: `npm run typecheck` verifies TypeScript contracts
- Jest: `npm test` verifies push token security logic

## HTTP Verification (No Device Required)

Parent can verify push token API contracts directly:

```bash
# 1. Register test patient and get tokens
PATIENT_TOKEN="..." # From user registration flow

# 2. Register push token
curl -X POST http://127.0.0.1:8001/api/v1/patients/{patient_id}/push_token \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "test-token-123", "platform": "android"}'

# 3. Verify exclusive binding (register same token with different patient)
PATIENT_B_TOKEN="..." 
curl -X POST http://127.0.0.1:8001/api/v1/patients/{patient_b_id}/push_token \
  -H "Authorization: Bearer $PATIENT_B_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "test-token-123", "platform": "android"}'

# 4. Verify ownership transferred (query database)
psql -U postgres -d cyberepi -c "SELECT * FROM push_tokens WHERE token = 'test-token-123';"

# 5. Deregister token
curl -X DELETE http://127.0.0.1:8001/api/v1/patients/me/push_token \
  -H "Authorization: Bearer $PATIENT_B_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "test-token-123", "platform": "android"}'

# 6. Verify stale DELETE protection (Patient A tries to delete Patient B's token)
curl -X DELETE http://127.0.0.1:8001/api/v1/patients/me/push_token \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "test-token-123", "platform": "android"}'
# Expected: 404 (token not bound to Patient A)
```
