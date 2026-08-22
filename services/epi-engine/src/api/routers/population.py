"""Population Intelligence API Router."""

import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import MobilityMatrix, RtEstimate, SpatialState

router = APIRouter(prefix="/api/v1", tags=["population"])

@router.get("/regions/{region_id}/Rt")
async def get_region_rt(
    region_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Fetch Rt estimates for last 30 days."""
    since = datetime.now(UTC) - timedelta(days=30)
    query = select(RtEstimate).where(
        RtEstimate.region_id == region_id,
        RtEstimate.patch_id.is_(None),
        RtEstimate.time >= since
    ).order_by(RtEstimate.time.asc())

    result = await db.execute(query)
    estimates = result.scalars().all()

    if not estimates:
        raise HTTPException(status_code=404, detail="No Rt estimates found for this region")

    return {
        "region_id": region_id,
        "dates": [e.time.isoformat() for e in estimates],
        "Rt_mean": [e.Rt_mean for e in estimates],
        "Rt_lower": [e.Rt_lower for e in estimates],
        "Rt_upper": [e.Rt_upper for e in estimates],
        "latest_Rt": estimates[-1].Rt_mean,
        "alert": estimates[-1].Rt_mean > 1.0
    }

@router.get("/map/hotspots")
async def get_hotspots(
    region_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
):
    """List hotspot patches with DP-noised estimates."""
    # In real implementation, we'd use Redis caching here
    query = select(SpatialState).where(
        SpatialState.region_id == region_id
    ).order_by(SpatialState.time.desc()).limit(100) # Latest per patch

    result = await db.execute(query)
    states = result.scalars().all()

    if not states:
        return []

    from src.population.hotspot import process_hotspot_states
    return await process_hotspot_states(states)

@router.post("/mobility/upload")
async def upload_mobility(
    region_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Authority uploads movement matrix as CSV."""
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Role 'physician' or 'admin' required to upload mobility matrices",
        )
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))

    # Required: from_patch_id, to_patch_id, fraction
    required = {"from_patch_id", "to_patch_id", "fraction"}
    if not required.issubset(df.columns):
        raise HTTPException(status_code=400, detail=f"CSV must contain columns: {required}")

    # Store in DB
    for _, row in df.iterrows():
        entry = MobilityMatrix(
            region_id=region_id,
            from_patch=str(row['from_patch_id']),
            to_patch=str(row['to_patch_id']),
            fraction=float(row['fraction'])
        )
        db.add(entry)

    await db.commit()
    return {"status": "success", "count": len(df)}
