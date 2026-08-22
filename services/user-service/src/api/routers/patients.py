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
                    search_resp = await client.get(
                        f"{settings.keycloak_admin_url}/users",
                        params={"email": body.email, "exact": "true"},
                        headers={"Authorization": f"Bearer {admin_token}"},
                    )
                    if search_resp.status_code == 200:
                        users = search_resp.json()
                        if users:
                            keycloak_id = users[0]["id"]
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

    # Look up by keycloak_id first so re-registration is idempotent.
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
    if row and row.risk_score is not None:
        return RiskResponse(
            patient_id=patient_id,
            risk_score=row.risk_score,
            risk_tier=row.risk_tier or "low",
        )
    return RiskResponse(patient_id=patient_id, risk_score=None, risk_tier="low")
