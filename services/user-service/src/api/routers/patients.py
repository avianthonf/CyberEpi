"""User-service API routers - registration, patient CRUD, push tokens, risk."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from shared.models import Patient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import record_audit
from src.auth import get_current_user
from src.config import settings
from src.db.models import PushToken
from src.db.session import get_db

router = APIRouter()


# ─── Pydantic Schemas ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=200)
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    region_id: str | None = Field(None, max_length=50)
    patch_id: str | None = Field(None, max_length=20)
    role: str = Field("patient", pattern=r"^patient$")


class RegisterResponse(BaseModel):
    id: uuid.UUID
    keycloak_id: str
    message: str = "Patient registered successfully"


class PatientResponse(BaseModel):
    id: uuid.UUID
    keycloak_id: str | None
    first_name: str | None
    last_name: str | None
    date_of_birth: str | None
    gender: str | None
    region_id: str | None
    patch_id: str | None
    email: str | None
    phone: str | None
    risk_tier: str

    model_config = {"from_attributes": True}


class PatientUpdateRequest(BaseModel):
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    date_of_birth: str | None = Field(None, max_length=20)
    gender: str | None = Field(None, max_length=20)
    region_id: str | None = Field(None, max_length=50)
    patch_id: str | None = Field(None, max_length=20)
    phone: str | None = Field(None, max_length=30)


class PushTokenRequest(BaseModel):
    token: str = Field(..., max_length=200)
    platform: str = Field(..., pattern=r"^(ios|android|web)$")


class RiskResponse(BaseModel):
    patient_id: uuid.UUID
    risk_score: float | None
    risk_tier: str


# ─── Auth Routes ─────────────────────────────────────────────────────
@router.post(
    "/api/v1/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_patient(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Register a new patient in Keycloak and patients table."""
    keycloak_id = ""
    try:
        async with httpx.AsyncClient() as client:
            # Get admin token via master realm admin-cli
            admin_realm = settings.keycloak_admin_realm
            token_resp = await client.post(
                f"{settings.keycloak_url}/realms/{admin_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": settings.keycloak_admin_client_id,
                    "username": settings.keycloak_admin_username,
                    "password": settings.keycloak_admin_password,
                },
            )
            if token_resp.status_code == 200:
                admin_token = token_resp.json().get("access_token", "")
                create_resp = await client.post(
                    f"{settings.keycloak_admin_url}/users",
                    json={
                        "username": body.email,
                        "email": body.email,
                        "firstName": body.first_name,
                        "lastName": body.last_name,
                        "enabled": True,
                        "credentials": [{"type": "password", "value": body.password, "temporary": False}],
                    },
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                if create_resp.status_code == 201:
                    location = create_resp.headers.get("Location", "")
                    keycloak_id = location.rsplit("/", 1)[-1] if location else ""
                elif create_resp.status_code == 409:
                    # User already exists in Keycloak. An unauthenticated caller attempting
                    # to register with an existing email should NOT receive the existing
                    # user's data. Return 409 to indicate the email is taken.
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An account with this email already exists. Please log in instead.",
                    )
    except httpx.HTTPError as exc:
        if not settings.debug:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Keycloak registration failed",
            ) from exc
        keycloak_id = str(uuid.uuid4())

    if not keycloak_id:
        if not settings.debug:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Keycloak registration returned no user ID",
            )
        keycloak_id = str(uuid.uuid4())

    # At this point, keycloak_id represents a newly created Keycloak user.
    # Look up by keycloak_id to link the Keycloak account to our Patient table.
    result = await db.execute(select(Patient).where(Patient.keycloak_id == keycloak_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        patient = Patient(
            keycloak_id=keycloak_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            region_id=body.region_id,
            patch_id=body.patch_id,
        )
        db.add(patient)
        await db.flush()
        await db.commit()
        await record_audit(db, actor_sub=keycloak_id, action="patient.register", patient_id=patient.id)

    return RegisterResponse(id=patient.id, keycloak_id=keycloak_id)


# ─── Patient CRUD ────────────────────────────────────────────────────
@router.get("/api/v1/patients/me", response_model=PatientResponse)
async def get_current_patient(
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> PatientResponse:
    """Get current authenticated patient's profile by JWT subject.

    Resolves JWT sub (Keycloak UUID) to local patient DB UUID.
    This is the canonical endpoint for mobile apps to get their patient_id.
    """
    keycloak_id = user.get("sub")
    if not keycloak_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    result = await db.execute(select(Patient).where(Patient.keycloak_id == keycloak_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient profile not found. Please complete registration.",
        )

    await record_audit(db, actor_sub=keycloak_id, action="patient.profile.read", patient_id=patient.id)
    return PatientResponse.model_validate(patient)


@router.get("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> PatientResponse:
    """Get patient profile by ID."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Ownership / RBAC check
    current_keycloak_id = _user.get("sub")
    roles = _user.get("realm_access", {}).get("roles", [])
    is_staff = any(r in ["physician", "admin"] for r in roles)

    if not is_staff and patient.keycloak_id != current_keycloak_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this profile",
        )

    await record_audit(db, actor_sub=str(current_keycloak_id), action="patient.read", patient_id=patient_id)
    return PatientResponse.model_validate(patient)


@router.put("/api/v1/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> PatientResponse:
    """Update patient profile."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Ownership / RBAC check
    current_keycloak_id = _user.get("sub")
    roles = _user.get("realm_access", {}).get("roles", [])
    is_staff = any(r in ["physician", "admin"] for r in roles)

    if not is_staff and patient.keycloak_id != current_keycloak_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this profile",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)

    await db.flush()
    await db.commit()
    await record_audit(db, actor_sub=str(_user.get("sub")), action="patient.update", patient_id=patient_id)
    return PatientResponse.model_validate(patient)


# ─── Push Tokens ─────────────────────────────────────────────────────
@router.post(
    "/api/v1/patients/{patient_id}/push_token",
    status_code=status.HTTP_201_CREATED,
)
async def register_push_token(
    patient_id: uuid.UUID,
    body: PushTokenRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Register an FCM/APNs push token for a patient."""
    # Check patient exists and authorize caller
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    roles = _user.get("realm_access", {}).get("roles", [])
    is_staff = any(r in ["physician", "admin"] for r in roles)
    if not is_staff and patient.keycloak_id != _user.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to register devices for this patient",
        )

    # Enforce exclusive token ownership: one token can only belong to one patient at a time
    # Use advisory lock on token to serialize concurrent transfers
    from sqlalchemy import text

    # Advisory lock keyed by hash of token string to serialize transfers
    lock_key = hash(body.token) % 2147483647  # PostgreSQL advisory lock range
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    # Remove this token from any other patient (transfer scenario)
    await db.execute(
        text("""
            DELETE FROM push_tokens 
            WHERE token = :token 
            AND platform = :platform 
            AND patient_id != :patient_id
        """),
        {"token": body.token, "platform": body.platform, "patient_id": str(patient_id)},
    )

    # Upsert for current patient
    await db.flush()
    await db.commit()
    return {"message": "Push token registered"}


@router.delete("/api/v1/patients/me/push_token", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_push_token(
    body: PushTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Deregister a push token for the authenticated patient.

    Idempotent: Returns 204 whether token was bound or not.
    Body: {"token": "...", "platform": "ios|android|web"}
    """
    # Resolve authenticated patient
    keycloak_id = user.get("sub")
    if not keycloak_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    result = await db.execute(select(Patient).where(Patient.keycloak_id == keycloak_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    # Delete token binding if it matches this patient
    from sqlalchemy import text

    await db.execute(
        text("""
            DELETE FROM push_tokens 
            WHERE patient_id = :patient_id 
            AND platform = :platform 
            AND token = :token
        """),
        {"patient_id": str(patient.id), "platform": body.platform, "token": body.token},
    )
    await db.commit()


# ─── Risk Score ──────────────────────────────────────────────────────
@router.get("/api/v1/patients/{patient_id}/risk", response_model=RiskResponse)
async def get_patient_risk(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> RiskResponse:
    """Get latest risk score and tier for a patient from vitals_ts."""
    from sqlalchemy import text

    # Ownership / RBAC check: patients may only read their own risk.
    roles = _user.get("realm_access", {}).get("roles", [])
    is_staff = any(r in ["physician", "admin"] for r in roles)
    if not is_staff:
        result = await db.execute(select(Patient.keycloak_id).where(Patient.id == patient_id))
        owner_keycloak_id = result.scalar_one_or_none()
        if owner_keycloak_id is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        if owner_keycloak_id != _user.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this patient's risk score",
            )

    result = await db.execute(
        text("SELECT risk_score, risk_tier FROM vitals_ts WHERE patient_id = :pid ORDER BY time DESC LIMIT 1"),
        {"pid": str(patient_id)},
    )
    row = result.first()
    await record_audit(db, actor_sub=str(_user.get("sub")), action="risk.read", patient_id=patient_id)
    if row and row.risk_score is not None:
        return RiskResponse(
            patient_id=patient_id,
            risk_score=row.risk_score,
            risk_tier=row.risk_tier or "low",
        )
    return RiskResponse(patient_id=patient_id, risk_score=None, risk_tier="low")
