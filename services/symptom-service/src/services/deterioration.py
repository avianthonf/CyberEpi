from datetime import UTC, datetime
from typing import Any, ClassVar

import structlog

logger = structlog.get_logger()

try:
    import lightgbm as lgb
    import numpy as np
    import pandas as pd

    _HAS_ML_DEPS = True
except ImportError:  # ML extra not installed — heuristic mode only
    lgb = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    pd = None  # type: ignore[assignment]
    _HAS_ML_DEPS = False

# Heuristic fallback thresholds used only when no trained model is available.
# These are documented clinical heuristics, NOT ML predictions — the response
# includes `source` so callers can distinguish the two.
_SPO2_HOSP_THRESHOLD = 92.0
_SPO2_SLOPE_HOSP_THRESHOLD = -2.0


class DeteriorationPredictor:
    """
    Implements the clinical deterioration prediction model (Chapter 5.2).

    Loads LightGBM models from disk when paths are provided. When models are
    absent, the endpoint falls back to explicit SpO2 heuristics and reports
    `source: "heuristic"` so the response is honest about what produced it.
    """

    FEATURES: ClassVar[list[str]] = [
        "age",
        "n_comorbidities",
        "days_since_onset",
        "spo2_current",
        "spo2_slope_48h",
        "spo2_min_24h",
        "heart_rate_current",
        "hr_slope_48h",
        "fever_max_24h",
        "fever_duration_h",
        "risk_score_current",
        "risk_score_acceleration",
        "local_hosp_rate",
        "regional_Rt",
    ]

    def __init__(self, model_hosp_path: str | None = None, model_icu_path: str | None = None):
        self.model_hosp = None
        self.model_icu = None
        self.available = _HAS_ML_DEPS

        if model_hosp_path and _HAS_ML_DEPS:
            self.model_hosp = lgb.Booster(model_file=model_hosp_path)
        if model_icu_path and _HAS_ML_DEPS:
            self.model_icu = lgb.Booster(model_file=model_icu_path)

    @property
    def has_models(self) -> bool:
        return self.model_hosp is not None and self.model_icu is not None

    def predict(self, patient_features: dict[str, Any]) -> dict[str, Any]:
        """
        Runs inference for a single patient (Chapter 5.2.3).
        """
        if not _HAS_ML_DEPS:
            # ML dependencies not installed — use heuristic fallback
            p_hosp = 0.05
            if patient_features.get("spo2_current", 100) < _SPO2_HOSP_THRESHOLD:
                p_hosp = 0.85
            elif patient_features.get("spo2_slope_48h", 0) < _SPO2_SLOPE_HOSP_THRESHOLD:
                p_hosp = 0.45
            p_icu = 0.01
            source = "heuristic"
        else:
            x = np.array([[patient_features.get(f, 0.0) for f in self.FEATURES]])

            if self.has_models:
                p_hosp = float(self.model_hosp.predict(x)[0])
                p_icu = float(self.model_icu.predict(x)[0])
                source = "ml"
            else:
                # Documented clinical heuristics — no model loaded.
                p_hosp = 0.05
                if patient_features.get("spo2_current", 100) < _SPO2_HOSP_THRESHOLD:
                    p_hosp = 0.85
                elif patient_features.get("spo2_slope_48h", 0) < _SPO2_SLOPE_HOSP_THRESHOLD:
                    p_hosp = 0.45
                p_icu = 0.01
                source = "heuristic"

        # Generate rule-based alerts (Chapter 5.2.3)
        alerts = []
        if patient_features.get("spo2_slope_48h", 0) < -1.0 and patient_features.get("spo2_current", 100) < 95:
            alerts.append("URGENT: Falling SpO2 detected")

        if patient_features.get("risk_score_acceleration", 1.0) > 1.5:
            alerts.append("RAPID DETERIORATION: Risk score increased >50% in 48h")

        return {
            "p_hospitalization_72h": float(p_hosp),
            "p_icu_7d": float(p_icu),
            "alerts": alerts,
            "source": source,
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }

    def train(self, X_train, y_hosp, y_icu):
        """
        Trains/Calibrates the models (Chapter 5.2.3).

        Requires the `[ml]` extra (lightgbm, pandas). Without it, training is
        unavailable and the predictor stays in heuristic mode.
        """
        if not _HAS_ML_DEPS:
            logger.error("ml_deps_missing_training_unavailable")
            raise RuntimeError("lightgbm/pandas not installed — install the [ml] extra to train")

        logger.info("training_deterioration_model", n_samples=len(X_train))

        params = {
            "objective": "binary",
            "metric": "auc",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "class_weight": "balanced",
            "random_state": 42,
            "verbose": -1,
        }

        # Train Hospitalization model
        dtrain_hosp = lgb.Dataset(X_train[self.FEATURES], label=y_hosp)
        self.model_hosp = lgb.train(params, dtrain_hosp, num_boost_round=100)

        # Train ICU model
        dtrain_icu = lgb.Dataset(X_train[self.FEATURES], label=y_icu)
        self.model_icu = lgb.train(params, dtrain_icu, num_boost_round=100)

        logger.info("training_complete")
