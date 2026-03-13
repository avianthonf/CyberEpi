"""Prescription-service API – CRUD, drug interactions via OpenFDA/RxNorm."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.config import settings
from src.db.models import Patient, Prescription
from src.db.session import get_db

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────
class PrescriptionCreate(BaseModel):
    patient_id: uuid.UUID
    drug_name: str
    ndc_code: str | None = None
    rxnorm_id: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    start_date: date
    end_date: date | None = None
    notes: str | None = None


class PrescriptionResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    drug_name: str
    ndc_code: str | None
    rxnorm_id: str | None
    dosage: str | None
    frequency: str | None
    status: str
    start_date: date
    end_date: date | None
    notes: str | None
    interactions: list[dict[str, Any]] | None = None

    model_config = {"from_attributes": True}


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(active|paused|completed|cancelled)$")


class MedicationScanRequest(BaseModel):
    ocr_text: str
    patient_id: uuid.UUID | None = None


class MedicationScanResponse(BaseModel):
    drug_name: str | None
    ndc_code: str | None
    rxnorm_id: str | None
    interactions: list[dict[str, Any]]


from src.services.interactions import (
    cached_fda_lookup,
    rxnorm_lookup,
    check_interactions,
)



# ─── Endpoints ────────────────────────────────────────────────────
@router.post(
    "/api/v1/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prescription(
    body: PrescriptionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> PrescriptionResponse:
    """Create a prescription and check for drug interactions."""
    # Authorization: Patient can only create for themselves.
    user_id = user.get("sub")
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        if str(body.patient_id) != user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only create prescriptions for themselves."
            )
    # Verify patient exists
    patient = await db.execute(select(Patient).where(Patient.id == body.patient_id))
    if not patient.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    redis_client: aioredis.Redis = request.app.state.redis

    # Resolve RxNorm ID if not provided
    rxnorm_id = body.rxnorm_id
    if not rxnorm_id:
        rxnorm_id = await _rxnorm_lookup(body.drug_name)

    # Check interactions
    interactions: list[dict[str, Any]] = []
    if rxnorm_id:
        interactions = await _check_interactions(redis_client, rxnorm_id, body.patient_id, db)

    # FDA lookup
    if body.ndc_code:
        await _cached_fda_lookup(redis_client, body.ndc_code)

    rx = Prescription(
        patient_id=body.patient_id,
        drug_name=body.drug_name,
        ndc_code=body.ndc_code,
        rxnorm_id=rxnorm_id,
        dosage=body.dosage,
        frequency=body.frequency,
        start_date=body.start_date,
        end_date=body.end_date,
        notes=body.notes,
    )
    db.add(rx)
    await db.flush()
    await db.commit()

    resp = PrescriptionResponse.model_validate(rx)
    resp.interactions = interactions
    return resp


@router.get("/api/v1/prescriptions/{rx_id}", response_model=PrescriptionResponse)
async def get_prescription(
    rx_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> PrescriptionResponse:
    result = await db.execute(select(Prescription).where(Prescription.id == rx_id))
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Authorization
    user_id = user.get("sub")
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        if str(rx.patient_id) != user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only view their own prescriptions."
            )

    return PrescriptionResponse.model_validate(rx)


@router.get("/api/v1/patients/{patient_id}/prescriptions", response_model=list[PrescriptionResponse])
async def list_prescriptions(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[PrescriptionResponse]:
    # Authorization
    user_id = user.get("sub")
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        if str(patient_id) != user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only list their own prescriptions."
            )
    result = await db.execute(
        select(Prescription).where(
            Prescription.patient_id == patient_id,
            Prescription.status == "active",
        )
    )
    return [PrescriptionResponse.model_validate(rx) for rx in result.scalars().all()]


@router.put("/api/v1/prescriptions/{rx_id}/status", response_model=PrescriptionResponse)
async def update_prescription_status(
    rx_id: uuid.UUID,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> PrescriptionResponse:
    result = await db.execute(select(Prescription).where(Prescription.id == rx_id))
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Authorization
    user_id = user.get("sub")
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        if str(rx.patient_id) != user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only update their own prescriptions."
            )
    rx.status = body.status
    await db.flush()
    await db.commit()
    return PrescriptionResponse.model_validate(rx)


@router.post("/api/v1/medications/scan", response_model=MedicationScanResponse)
async def scan_medication(
    body: MedicationScanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> MedicationScanResponse:
    """OCR text → OpenFDA lookup → interaction check."""
    redis_client: aioredis.Redis = request.app.state.redis

    # Extract drug name from OCR text (simplified: use first line or full text)
    drug_name = body.ocr_text.strip().split("\n")[0].strip()

    # RxNorm lookup
    rxnorm_id = await _rxnorm_lookup(drug_name)

    # FDA lookup by guessing NDC from text
    ndc_code: str | None = None
    fda_result: dict[str, Any] | None = None

    # Try to find NDC pattern in text (XXXXX-XXXX-XX)
    import re

    ndc_match = re.search(r"\d{4,5}-\d{3,4}-\d{1,2}", body.ocr_text)
    if ndc_match:
        ndc_code = ndc_match.group()
        fda_result = await _cached_fda_lookup(redis_client, ndc_code)
        if fda_result and not rxnorm_id:
            drug_name = fda_result.get("brand_name", drug_name)

    # Check interactions if patient provided
    interactions: list[dict[str, Any]] = []
    if rxnorm_id and body.patient_id:
        interactions = await _check_interactions(redis_client, rxnorm_id, body.patient_id, db)

    return MedicationScanResponse(
        drug_name=drug_name,
        ndc_code=ndc_code,
        rxnorm_id=rxnorm_id,
        interactions=interactions,
    )
