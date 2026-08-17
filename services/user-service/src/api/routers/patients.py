"""User-service API routers – registration, patient CRUD, push tokens, risk."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.config import settings
from src.db.models import Patient, PushToken
from src.db.session import get_db

router = APIRouter()


# ─── Pydantic Schemas ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str
    last_name: str
    region_id: str | None = None
    patch_id: str | None = None


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
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    region_id: str | None = None
    patch_id: str | None = None
    phone: str | None = None


class PushTokenRequest(BaseModel):
    token: str
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
            # Get admin token
            token_resp = await client.post(
                settings.keycloak_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.keycloak_client_id,
                    "client_secret": settings.keycloak_client_secret,
                },
            )
            if token_resp.status_code == 200:
                admin_token = token_resp.json().get("access_token", "")
                # Create user
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
    except httpx.HTTPError as exc:
        # Only fall back to a fake Keycloak ID in dev; in prod this must fail
        # loudly rather than silently creating patients who can never log in.
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

    # Create patient record
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

    return RegisterResponse(id=patient.id, keycloak_id=keycloak_id)


# ─── Patient CRUD ────────────────────────────────────────────────────
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
    # Check patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    # Upsert push token
    existing = await db.execute(
        select(PushToken).where(
            PushToken.patient_id == patient_id,
            PushToken.platform == body.platform,
        )
    )
    token_record = existing.scalar_one_or_none()
    if token_record:
        token_record.token = body.token
    else:
        db.add(
            PushToken(
                patient_id=patient_id,
                token=body.token,
                platform=body.platform,
            )
        )
    await db.flush()
    await db.commit()
    return {"message": "Push token registered"}


# ─── Risk Score ──────────────────────────────────────────────────────
@router.get("/api/v1/patients/{patient_id}/risk", response_model=RiskResponse)
async def get_patient_risk(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> RiskResponse:
    """Get latest risk score and tier for a patient from vitals_ts."""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT risk_score, risk_tier FROM vitals_ts WHERE patient_id = :pid ORDER BY time DESC LIMIT 1"),
        {"pid": str(patient_id)},
    )
    row = result.first()
    if row and row.risk_score is not None:
        return RiskResponse(
            patient_id=patient_id,
            risk_score=row.risk_score,
            risk_tier=row.risk_tier or "low",
        )
    return RiskResponse(patient_id=patient_id, risk_score=None, risk_tier="low")
