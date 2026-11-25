"""Background task: consume Kafka `symptom-reports` events and run the
FilterOrchestrator + Rt estimator per region.

This is the missing runtime wiring: the orchestrator is implemented but
nothing in the request path invokes it. Without this consumer, the
`GET /regions/{id}/state` and `GET /regions/{id}/Rt` endpoints would
never return anything because no observation ever advances the filter.

For each event we:
  1. Load EpiParams for the region.
  2. Run the orchestrator (EKF/PF) to update filter state in Redis.
  3. Compute Rt from the latest state and persist a row in `rt_estimates`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.errors import KafkaError
from seir_core import SEIRParams
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.config import settings
from src.db.connection import AsyncSessionLocal
from src.db.models import EpiParams, RtEstimate
from src.filters.orchestrator import FilterOrchestrator

logger = structlog.get_logger()


def _seir_params_from_row(row: EpiParams) -> SEIRParams:
    return SEIRParams(
        beta=row.beta,
        sigma=row.sigma,
        gamma=row.gamma,
        rho=row.rho,
        fA=row.fA,
        fM=row.fM,
        fS=row.fS,
        alpha=row.alpha,
        h_rate=row.h_rate,
        delta=row.delta,
        mu=row.mu,
        mu_icu=row.mu_icu,
        gamma_A=row.gamma_A,
        gamma_M=row.gamma_M,
        gamma_S=row.gamma_S,
        gamma_H=row.gamma_H,
        gamma_ICU=row.gamma_ICU,
        papp=row.papp,
        N_pop=row.N_pop,
    )


def _observations_from_event(event: dict) -> dict:
    """Map a symptom-report event to the orchestrator's observation schema.

    The orchestrator expects: app_reports, confirmed_cases,
    hospital_admissions, pharmacy_proxy, wastewater. We approximate
    confirmed_cases and admissions from risk_score and risk_tier when the
    upstream publishers don't send real counts yet.
    """
    payload_raw = event.get("payload") or "{}"
    try:
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    except (TypeError, json.JSONDecodeError):
        payload = {}
    risk_score = float(payload.get("risk_score") or event.get("risk_score") or 0.0)
    symptoms = payload.get("symptoms") or event.get("symptoms") or []
    return {
        "app_reports": 1.0,
        "confirmed_cases": max(0.0, 50.0 * risk_score),
        "hospital_admissions": max(0.0, 10.0 * risk_score),
        "pharmacy_proxy": float(len(symptoms)),
        "wastewater": 0.0,
    }


def _compute_rt(params: SEIRParams, x_state: list[float]) -> tuple[float, float, float]:
    """Compute a simple Rt estimate from the current filter state.

    Rt ≈ (β · S / N) / γ. Heuristic ±20% display bounds; not calibrated/posterior
    confidence intervals. The API contract (Rt_mean/Rt_lower/Rt_upper) is fulfilled
    even before we have enough posterior samples to derive empirical quantiles.
    """
    S = float(x_state[0]) if x_state else params.N_pop * 0.9
    N = float(params.N_pop)
    beta = float(params.beta)
    gamma = float(params.gamma)
    rt = (beta * S / max(N, 1.0)) / max(gamma, 1e-6)
    rt = max(0.0, rt)
    return rt, rt * 0.8, rt * 1.2


async def _process_batch(
    events: Iterable[dict],
    redis_client,
    kafka_producer,
) -> None:
    """Process a batch of events; aggregate per region before running the filter."""
    by_region: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        region = ev.get("region_id")
        if region:
            by_region[region].append(ev)

    logger.info("epi_observation_batch", events=sum(len(v) for v in by_region.values()), regions=len(by_region))

    if not by_region:
        return

    async with AsyncSessionLocal() as db:
        for region_id, region_events in by_region.items():
            result = await db.execute(select(EpiParams).where(EpiParams.region_id == region_id))
            params_row = result.scalar_one_or_none()
            if params_row is None:
                logger.debug("region_params_missing", region_id=region_id)
                continue

            params = _seir_params_from_row(params_row)
            orchestrator = FilterOrchestrator(
                region_id,
                redis_client,
                kafka_producer,
                session_maker=AsyncSessionLocal,
            )

            x_state: list[float] = []
            for ev in region_events:
                obs = _observations_from_event(ev)
                try:
                    result_obj = await orchestrator.process_observation(params, obs)
                except Exception:
                    logger.exception("orchestrator_failed", region_id=region_id)
                    continue
                x_state = [result_obj.state[k] for k in ("S", "E", "IA", "IM", "IS", "H", "ICU", "R", "D")]
                x_state += [
                    result_obj.obs_params.get("papp", params.papp),
                    result_obj.obs_params.get("ptest", 0.5),
                    result_obj.obs_params.get("kappa", 0.1),
                ]

            if not x_state:
                continue

            rt_mean, rt_lower, rt_upper = _compute_rt(params, x_state)
            now = datetime.now(UTC)
            stmt = (
                pg_insert(RtEstimate)
                .values(
                    time=now,
                    region_id=region_id,
                    patch_id=None,
                    Rt_mean=rt_mean,
                    Rt_lower=rt_lower,
                    Rt_upper=rt_upper,
                    window_days=7,
                )
                .on_conflict_do_nothing(index_elements=["time", "region_id"])
            )
            await db.execute(stmt)
        await db.commit()


async def consume_observations(app) -> None:
    """Run forever: consume `symptom-reports` and feed the orchestrator.

    Uses manual partition assignment (no consumer group) so we don't depend
    on group coordination — the broker in this environment is single-node and
    group rebalances are unreliable.
    """
    backoff = 1.0
    while True:
        consumer = AIOKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            enable_auto_commit=False,
            auto_offset_reset="latest",
        )
        try:
            await consumer.start()
            tp = TopicPartition("symptom-reports", 0)
            consumer.assign([tp])
            await consumer.seek_to_end(tp)
            logger.info("epi_observation_consumer_started", topic="symptom-reports")
            backoff = 1.0
            batch: list[dict] = []
            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(consumer.getone(), timeout=2.0)
                    except TimeoutError:
                        if batch:
                            await _process_batch(batch, app.state.redis, app.state.kafka_producer)
                            batch.clear()
                        continue
                    try:
                        event = json.loads(msg.value.decode("utf-8"))
                        batch.append(event)
                        if len(batch) >= 25:
                            await _process_batch(batch, app.state.redis, app.state.kafka_producer)
                            batch.clear()
                    except Exception:
                        logger.exception("observation_decode_error")
            finally:
                if batch:
                    try:
                        await _process_batch(batch, app.state.redis, app.state.kafka_producer)
                    except Exception:
                        logger.exception("final_batch_flush_failed")
                    batch.clear()
                with contextlib.suppress(Exception):
                    await consumer.stop()
        except KafkaError as exc:
            logger.warning("epi_consumer_kafka_error", error=str(exc), backoff=backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("epi_consumer_crashed")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
