"""Continuous surveillance feed ingestion for epi-engine.

Downloads the FluSight forecast-hub target files (which mirror CDC NHSN
weekly influenza hospital admissions and NSSP ED influenza visit fractions),
upserts them into `surveillance_observations`, and feeds new weeks into the
per-region filter orchestrator (`hospital_admissions` + ILI mapped onto the
`pharmacy_proxy` healthcare-seeking channel whose coupling `kappa` is learned
as part of the filter state).

Runs as a periodic background task in the API process (lifespan-managed) —
fully automatic, no human input required. A one-shot CLI is provided:

    python -m src.tasks.surveillance_ingest --once
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.config import settings

logger = structlog.get_logger()

_LOCATIONS_CSV = os.path.join(os.path.dirname(__file__), "data",
                              "flusight_locations.csv")
_POP_CAP = 60_000_000  # guard against parsing a bad locations table


def load_location_populations() -> dict[str, float]:
    """FIPS/'US' -> population from the bundled hub locations table."""
    pops: dict[str, float] = {}
    with open(_LOCATIONS_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            loc = row["location"]
            try:
                pops[loc] = float(row["population"])
            except (KeyError, ValueError):
                continue
    return pops


async def _fetch_csv(client: httpx.AsyncClient, url: str) -> list[dict]:
    resp = await client.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


async def fetch_weekly(
    client: httpx.AsyncClient | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Fetch both feeds; return merged records keyed by (region_id, week_end).

    Record: {region_id, week_end, admissions, ili_frac}
    """
    close = client is None
    client = client or httpx.AsyncClient()
    try:
        adm_rows, ili_rows = await asyncio.gather(
            _fetch_csv(client, settings.surveillance_admissions_url),
            _fetch_csv(client, settings.surveillance_ili_url),
        )
    finally:
        if close:
            await client.aclose()

    merged: dict[tuple[str, datetime], dict] = {}

    def _put(loc: str, date_s: str, field: str, value: float | None) -> None:
        if value is None:
            return
        week_end = datetime.fromisoformat(date_s).replace(tzinfo=UTC)
        if since is not None and week_end < since:
            return
        rec = merged.setdefault((loc, week_end), {
            "region_id": loc, "week_end": week_end,
            "admissions": None, "ili_frac": None,
        })
        rec[field] = value

    for r in adm_rows:
        try:
            _put(r["location"], r["date"], "admissions", float(r["value"]))
        except (KeyError, ValueError):
            continue
    for r in ili_rows:
        try:
            _put(r["location"], r["date"], "ili_frac", float(r["value"]))
        except (KeyError, ValueError):
            continue
    return list(merged.values())


async def upsert_observations(records: list[dict]) -> int:
    """Idempotent upsert into surveillance_observations."""
    if not records:
        return 0
    # Imports are deferred so the module is importable without a DB.
    from src.db.connection import AsyncSessionLocal
    from src.db.models import SurveillanceObservation

    now = datetime.now(UTC)
    rows = [{
        "region_id": r["region_id"],
        "week_end": r["week_end"],
        "admissions": r["admissions"],
        "ili_fraction": r["ili_frac"],
        "source": "flusight-hub-target",
        "fetched_at": now,
    } for r in records]
    stmt = pg_insert(SurveillanceObservation)
    stmt = stmt.on_conflict_do_update(
        index_elements=["region_id", "week_end"],
        set_={
            "admissions": stmt.excluded.admissions,
            "ili_fraction": stmt.excluded.ili_fraction,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    async with AsyncSessionLocal() as db:
        # 6 bind params/row; asyncpg caps a prepared statement at 32767 args.
        for i in range(0, len(rows), 4000):
            await db.execute(stmt, rows[i:i + 4000])
        await db.commit()
    return len(rows)


async def apply_to_filters(records: list[dict], redis_client=None,
                           kafka_producer=None) -> int:
    """Push new weekly records into region filters.

    Only regions that have an EpiParams row (i.e. a registered model) are
    updated. ILI fraction is scaled to a healthcare-seeking count via the
    region population so it lands in the filter's `pharmacy_proxy` channel.
    """
    from src.db.connection import AsyncSessionLocal
    from src.db.models import EpiParams
    from src.filters.orchestrator import FilterOrchestrator
    from src.tasks.observation_consumer import _seir_params_from_row

    pops = load_location_populations()
    if redis_client is None:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_url)
        own_redis = True
    else:
        own_redis = False

    n = 0
    try:
        async with AsyncSessionLocal() as db:
            param_rows = (await db.execute(select(EpiParams))).scalars().all()
            known = {r.region_id: _seir_params_from_row(r) for r in param_rows}

        for rec in records:
            params = known.get(rec["region_id"])
            if params is None:
                continue
            pop = pops.get(rec["region_id"], getattr(params, "N_pop", 0) or 0) or 1.0
            pop = min(pop, _POP_CAP)
            obs = {
                "app_reports": float("nan"),
                "confirmed_cases": float("nan"),
                "hospital_admissions": rec["admissions"] or float("nan"),
                "pharmacy_proxy": (rec["ili_frac"] or float("nan")) * pop,
                "wastewater": float("nan"),
            }
            orch = FilterOrchestrator(
                region_id=rec["region_id"], redis_client=redis_client,
                kafka_producer=kafka_producer, session_maker=AsyncSessionLocal,
            )
            try:
                await orch.process_observation(params, obs)
                n += 1
            except Exception as exc:  # noqa: BLE001 — filter failure for one region must not sink the batch
                logger.warning("filter update failed", region=rec["region_id"],
                               error=str(exc))
    finally:
        if own_redis:
            await redis_client.aclose()
    return n


async def run_once(app=None) -> dict:
    """Single ingest cycle: fetch → persist → filter updates."""
    from datetime import timedelta

    since = (datetime.now(UTC)
             - timedelta(weeks=settings.surveillance_backfill_weeks))
    stats = {"fetched": 0, "upserted": 0, "filtered": 0}
    records = await fetch_weekly(since=since)
    stats["fetched"] = len(records)
    stats["upserted"] = await upsert_observations(records)

    # Only the newest complete week drives the filter (older weeks are
    # backfill for history, not new evidence).
    if records:
        newest = max(r["week_end"] for r in records)
        latest = [r for r in records if r["week_end"] == newest]
        stats["filtered"] = await apply_to_filters(
            latest,
            redis_client=getattr(app.state, "redis", None) if app else None,
            kafka_producer=(getattr(app.state, "kafka_producer", None)
                            if app else None),
        )
    logger.info("surveillance ingest complete", **stats)
    return stats


async def ingest_loop(app) -> None:
    """Forever: ingest now, then sleep `surveillance_refresh_seconds`."""
    logger.info("surveillance ingest loop starting",
                interval_s=settings.surveillance_refresh_seconds)
    backoff = 60.0
    while True:
        try:
            await run_once(app)
            backoff = 60.0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — supervisor loop: retry forever on transient network/DB errors
            logger.warning("surveillance ingest failed",
                           error=str(exc), retry_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 1800.0)
            continue
        await asyncio.sleep(settings.surveillance_refresh_seconds)


def main() -> None:
    from src.db.connection import AsyncSessionLocal, engine  # noqa: F401
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        stats = asyncio.run(run_once())
        print(stats)
    else:
        parser.error("only --once is supported for the standalone CLI")


if __name__ == "__main__":
    main()
