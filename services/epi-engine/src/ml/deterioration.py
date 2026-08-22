import os
from datetime import UTC, datetime
from typing import Any

import numpy as np

try:
    import lightgbm as lgb
    import shap

    _HAS_ML_DEPS = True
except ImportError:  # [ml] extra not installed
    lgb = None  # type: ignore[assignment]
    shap = None  # type: ignore[assignment]
    _HAS_ML_DEPS = False

FEATURES = [
    'age', 'n_comorbidities', 'days_since_onset',
    'spo2_current', 'spo2_slope_48h', 'spo2_min_24h',
    'heart_rate_current', 'hr_slope_48h',
    'fever_max_24h', 'fever_duration_h',
    'risk_score_current', 'risk_score_acceleration',
    'adherence_rate_7d', 'n_missed_doses_24h',
    'local_hosp_rate', 'regional_Rt'
]

MODEL_DIR = os.getenv("MODEL_DIR", "/models/")


class DeteriorationModel:
    def __init__(self):
        self.params = {
            'objective': 'binary',
            'metric': 'auc',
            'learning_rate': 0.05,
            'num_leaves': 31,
            'min_child_samples': 20,
            'n_estimators': 500,
            'class_weight': 'balanced',
        }
        self.model_hosp = None
        self.model_icu = None
        self.explainer_hosp = None
        self.explainer_icu = None
        self.available = _HAS_ML_DEPS

    @property
    def has_models(self) -> bool:
        return self.model_hosp is not None and self.model_icu is not None

    def train(self, X_train: np.ndarray, y_train_hosp: np.ndarray, y_train_icu: np.ndarray):
        """Train models and compute explainers."""
        if not _HAS_ML_DEPS:
            raise RuntimeError("lightgbm/shap not installed — install the [ml] extra to train")
        self.model_hosp = lgb.LGBMClassifier(**self.params)
        self.model_hosp.fit(X_train, y_train_hosp)

        self.model_icu = lgb.LGBMClassifier(**self.params)
        self.model_icu.fit(X_train, y_train_icu)

        self.explainer_hosp = shap.TreeExplainer(self.model_hosp)
        self.explainer_icu = shap.TreeExplainer(self.model_icu)

    def save_models(self):
        """Save models to versioned directory."""
        if not os.path.exists(MODEL_DIR):
            os.makedirs(MODEL_DIR)
        date_str = datetime.now(UTC).strftime("%Y%m%d")

        hosp_path = os.path.join(MODEL_DIR, f"model_hosp_{date_str}.txt")
        icu_path = os.path.join(MODEL_DIR, f"model_icu_{date_str}.txt")

        if self.model_hosp:
            self.model_hosp.booster_.save_model(hosp_path)
        if self.model_icu:
            self.model_icu.booster_.save_model(icu_path)

    def load_models(self, date_str: str):
        if not _HAS_ML_DEPS:
            return
        hosp_path = os.path.join(MODEL_DIR, f"model_hosp_{date_str}.txt")
        icu_path = os.path.join(MODEL_DIR, f"model_icu_{date_str}.txt")

        if os.path.exists(hosp_path):
            self.model_hosp = lgb.Booster(model_file=hosp_path)
            self.explainer_hosp = shap.TreeExplainer(self.model_hosp)
        if os.path.exists(icu_path):
            self.model_icu = lgb.Booster(model_file=icu_path)
            self.explainer_icu = shap.TreeExplainer(self.model_icu)

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        # Validate feature count
        if len(features) != 16:
            raise ValueError("Expected exact 16 features")

        x_array = np.array([[features.get(f, 0.0) for f in FEATURES]])

        # Calculate thresholds for alerts
        alerts = []
        if features.get('spo2_slope_48h', 0) < -1.0 and features.get('spo2_current', 100) < 95:
            alerts.append("URGENT")
        if features.get('risk_score_acceleration', 0) > 1.5:
            alerts.append("RAPID_DETERIORATION")

        if not self.has_models:
            raise RuntimeError(
                "No trained model available — train or load models before predicting"
            )

        if hasattr(self.model_hosp, 'predict_proba'):
            p_hosp = float(self.model_hosp.predict_proba(x_array)[0][1])
            p_icu = float(self.model_icu.predict_proba(x_array)[0][1])
            raw_shap = self.explainer_hosp.shap_values(x_array)
        else:
            # lightgbm booster predict returns proba for binary
            p_hosp = float(self.model_hosp.predict(x_array)[0])
            p_icu = float(self.model_icu.predict(x_array)[0])
            raw_shap = self.explainer_hosp.shap_values(x_array)

        # SHAP returns a single array for binary in recent versions; older
        # versions return [class0, class1]. Normalize to the positive class.
        shap_vals = raw_shap[1][0] if isinstance(raw_shap, list) else raw_shap[0]

        # compute top 5 shap features
        shap_abs = np.abs(shap_vals)
        top5_idx = np.argsort(shap_abs)[-5:][::-1]

        shap_top5 = []
        for idx in top5_idx:
            shap_top5.append({
                "feature": FEATURES[idx],
                "value": float(x_array[0][idx]),
                "impact": float(shap_vals[idx]),
            })

        expected = getattr(self.explainer_hosp, "expected_value", 0)
        if isinstance(expected, (list, np.ndarray)) and len(expected) > 1:
            expected = expected[1]
        elif isinstance(expected, np.ndarray):
            expected = expected[0]

        return {
            "p_hosp_72h": p_hosp,
            "p_icu_7d": p_icu,
            "alerts": alerts,
            "shap_top5": shap_top5,
            "expected_value": float(expected),
            "shap": shap_vals.tolist(),  # For testing full sum
        }
