"""Prescription drug interactions service."""

import json
import httpx
import asyncio
import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from typing import Any

from src.config import settings
from src.db.models import Prescription

logger = structlog.get_logger()

async def _retry_get(client, url, params=None, max_retries=3):
    """Internal helper for retrying GET requests with exponential backoff."""
    for i in range(max_retries):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
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
    except Exception as e:
        logger.error("OpenFDA lookup failed persistently", ndc=ndc_code, error=str(e))
    return None

async def rxnorm_lookup(drug_name: str) -> str | None:
    """Get RxNorm ID for a drug name."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await _retry_get(
                client,
                f"{settings.rxnorm_api_url}/rxcui.json",
                params={"name": drug_name}
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                id_group = data.get("idGroup", {})
                rxnorm_ids = id_group.get("rxnormId", [])
                return rxnorm_ids[0] if rxnorm_ids else None
    except Exception as e:
        logger.error("RxNorm lookup failed persistently", drug_name=drug_name, error=str(e))
    return None

async def check_interactions(
    redis_client: aioredis.Redis,
    rxnorm_id: str,
    patient_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Check drug interactions against patient's active prescriptions (optimized)."""
    result = await db.execute(
        select(Prescription).where(
            Prescription.patient_id == patient_id,
            Prescription.status == "active",
        )
    )
    active_rxs = [rx for rx in result.scalars().all() if rx.rxnorm_id and rx.rxnorm_id != rxnorm_id]
    if not active_rxs:
        return []

    # Prepare cache keys
    id_pairs = [(min(rxnorm_id, rx.rxnorm_id), max(rxnorm_id, rx.rxnorm_id), rx) for rx in active_rxs]
    cache_keys = [f"fda:interaction:{p[0]}:{p[1]}" for p in id_pairs]

    # Batch Redis lookup
    cached_responses = await redis_client.mget(*cache_keys)
    
    interactions: list[dict[str, Any]] = []
    missing_pairs = []

    for i, cached in enumerate(cached_responses):
        if cached:
            cached_data = json.loads(cached)
            if cached_data:
                interactions.extend(cached_data)
        else:
            missing_pairs.append(id_pairs[i])

    if not missing_pairs:
        return interactions

    # Parallel API calls for missing pairs
    async def fetch_and_cache(p_info):
        drug_a, drug_b, rx = p_info
        key = f"fda:interaction:{drug_a}:{drug_b}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await _retry_get(
                    client,
                    f"{settings.rxnorm_api_url}/interaction/list.json",
                    params={"rxcuis": f"{drug_a}+{drug_b}"}
                )
                if resp and resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get("fullInteractionTypeGroup", [])
                    found: list[dict[str, Any]] = []
                    for group in pairs:
                        for itype in group.get("fullInteractionType", []):
                            for pair in itype.get("interactionPair", []):
                                found.append(
                                    {
                                        "severity": pair.get("severity", "unknown"),
                                        "description": pair.get("description", ""),
                                        "drug_a": drug_a,
                                        "drug_b": drug_b,
                                        "drug_b_name": rx.drug_name,
                                    }
                                )
                    await redis_client.setex(key, settings.fda_cache_ttl, json.dumps(found))
                    return found
        except Exception as e:
            logger.error("Interaction check failed persistently", rxnorm_id=drug_a, other_rxnorm_id=drug_b, error=str(e))
        return []

    results = await asyncio.gather(*(fetch_and_cache(p) for p in missing_pairs))
    for res in results:
        interactions.extend(res)

    return interactions
