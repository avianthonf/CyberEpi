import json
from pathlib import Path

import redis.asyncio as aioredis
import structlog
from sqlalchemy import func, select, text

from src.db.models import VitalsTS

logger = structlog.get_logger()

_LIKELIHOODS_PATH = Path(__file__).resolve().parent.parent / "symptom_likelihoods.json"
with open(_LIKELIHOODS_PATH) as f:
    SYMPTOM_LIKELIHOODS: dict[str, dict[str, dict[str, float]]] = json.load(f)

RISK_THRESHOLDS = [
    (0.8, "urgent"),
    (0.6, "consult"),
    (0.3, "moderate"),
    (0.0, "low"),
]

def compute_risk_tier(score: float) -> str:
    for threshold, tier in RISK_THRESHOLDS:
        if score >= threshold:
            return tier
    return "low"

def compute_bayesian_risk(
    symptoms: list[str],
    prior: float = 0.01,
    disease: str = "influenza",
) -> float:
    likelihoods = SYMPTOM_LIKELIHOODS.get(disease, {})
    numerator = prior
    denominator_not = 1.0 - prior
    for symptom in symptoms:
        if symptom in likelihoods:
            p_s_given_i = likelihoods[symptom]["p_given_infected"]
            p_s_given_not_i = likelihoods[symptom]["p_given_not_infected"]
            numerator *= p_s_given_i
            denominator_not *= p_s_given_not_i
    total = numerator + denominator_not
    if total == 0:
        return 0.0
    return numerator / total

async def calculate_and_update_risk(db, request, body, region_id):
    # Count existing reports for this patient
    count_result = await db.execute(select(func.count()).select_from(VitalsTS).where(VitalsTS.patient_id == body.patient_id))
    report_count = (count_result.scalar() or 0) + 1  # +1 for current report

    risk_score: float | None = None
    risk_tier: str | None = None

    if report_count >= 3:
        prior = 0.01
        try:
            redis_client: aioredis.Redis = request.app.state.redis
            cached_state = await redis_client.get(f"filter_state:{region_id}")
            if cached_state:
                state_data = json.loads(cached_state)
                prior = float(state_data.get("prevalence", 0.01))
            else:
                logger.warning("no_filter_state_in_redis", region_id=region_id)
        except Exception as e:  # noqa: BLE001 - Redis outage should not block risk scoring
            logger.warning("risk_prior_fallback_to_default", error=str(e))

        symptoms = list(body.symptoms)
        if body.spo2 is not None and body.spo2 < 95:
            symptoms.append("spo2_low")

        risk_score = compute_bayesian_risk(symptoms, prior=prior)
        risk_tier = compute_risk_tier(risk_score)

        await db.execute(
            text("UPDATE patients SET risk_tier = :tier, updated_at = now() WHERE id = :pid"),
            {"tier": risk_tier, "pid": str(body.patient_id)},
        )
    return report_count, risk_score, risk_tier
