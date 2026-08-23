"""Prescription drug interactions service."""

import asyncio
import json
import uuid
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Prescription
from src.services.ddi_data import find_interactions

logger = structlog.get_logger()

async def _retry_get(client, url, params=None, max_retries=3):
    """Internal helper for retrying GET requests with exponential backoff."""
    for i in range(max_retries):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except (TimeoutError, httpx.HTTPError) as e:
            if i == max_retries - 1:
                logger.error("External API call failed after retries", url=url, error=str(e))
                raise
            wait = 2 ** i
            logger.warning("External API call failed, retrying...", url=url, error=str(e), attempt=i+1, wait=wait)
            await asyncio.sleep(wait)
    return None

async def cached_fda_lookup(
    redis_client: aioredis.Redis,
    ndc_code: str,
) -> dict[str, Any] | None:
    """Lookup drug by NDC via OpenFDA, with Redis cache."""
    cache_key = f"fda:ndc:{ndc_code}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await _retry_get(
                client,
                f"{settings.openfda_api_url}/drug/ndc.json",
                params={"search": f"product_ndc:{ndc_code}"}
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                result = data.get("results", [{}])[0] if data.get("results") else None
                if result:
                    await redis_client.setex(cache_key, settings.fda_cache_ttl, json.dumps(result))
                return result
    except Exception as e:  # noqa: BLE001 — external API boundary: degrades to None on any network/parse failure
        logger.error("OpenFDA lookup failed persistently", ndc=ndc_code, error=str(e))
    return None

async def rxnorm_lookup(drug_name: str) -> str | None:
    """Get RxNorm ID for a drug name."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{settings.rxnorm_api_url}/rxcui.json"
            logger.info("Calling RxNorm API", url=url, drug_name=drug_name)
            resp = await _retry_get(
                client,
                url,
                params={"name": drug_name}
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                id_group = data.get("idGroup", {})
                rxnorm_ids = id_group.get("rxnormId", [])
                return rxnorm_ids[0] if rxnorm_ids else None
    except Exception as e:  # noqa: BLE001 — external API boundary: degrades to None on any network/parse failure
        logger.error("RxNorm lookup failed persistently", drug_name=drug_name, error=str(e))
    logger.warning("RxNorm lookup failed to find drug", drug_name=drug_name)
    return None

async def check_interactions(
    db: AsyncSession,
    patient_id: uuid.UUID,
    new_drug_name: str,
) -> list[dict[str, Any]]:
    """Check new drug against patient's active prescriptions.

    Uses the bundled high-priority DDI table (`ddi_data`), replacing the
    discontinued NLM/RxNav interaction API. Local, deterministic, offline.
    """
    result = await db.execute(
        select(Prescription.drug_name).where(
            Prescription.patient_id == patient_id,
            Prescription.status == "active",
        )
    )
    active = [row[0] for row in result.all()]
    interactions = find_interactions([*active, new_drug_name])
    # only interactions involving the new drug are actionable here
    return [i for i in interactions if new_drug_name in i["drugs"]]
