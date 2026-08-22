# Privacy Service Scope Clarification

## Service Purpose
The privacy-service is focused on **ML Privacy** (Differential Privacy and Federated Learning), not PII-level GDPR compliance.

## Current Endpoints
- `POST /internal/dp/publish` - Publish differentially private aggregate data
- `POST /api/v1/fl/upload_gradient` - Upload federated learning gradients  
- `GET /api/v1/fl/model/{round_id}` - Retrieve global FL model
- `POST /api/v1/fl/trigger_aggregation` - Trigger FL aggregation

## GDPR/PII Privacy Handled Elsewhere
Patient data access, deletion, and audit logging should be handled by:
- **user-service**: Patient registration and profile management
- **Database-level**: Soft deletes, audit triggers, retention policies
- **API Gateway (Kong)**: Request logging and audit trails

## If GDPR Endpoints Needed in Future
Add to privacy-service:
- `POST /api/v1/gdpr/data-access-request` - Generate patient data export
- `POST /api/v1/gdpr/data-deletion-request` - Handle right to be forgotten
- `GET /api/v1/gdpr/audit-log/{patient_id}` - Audit trail retrieval

## Current Status
✅ Service scope is **ML privacy only** - this is acceptable for the current architecture.
No changes needed unless requirements explicitly add GDPR endpoint requirements.
