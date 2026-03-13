import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List

import numpy as np
import lightgbm as lgb
import shap

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
            'class_weight': 'balanced'
        }
        self.model_hosp = None
        self.model_icu = None
        self.explainer_hosp = None
        self.explainer_icu = None

    def train(self, X_train: np.ndarray, y_train_hosp: np.ndarray, y_train_icu: np.ndarray):
        """Train models and compute explainers."""
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
        date_str = datetime.now().strftime("%Y%m%d")
        
        hosp_path = os.path.join(MODEL_DIR, f"model_hosp_{date_str}.txt")
        icu_path = os.path.join(MODEL_DIR, f"model_icu_{date_str}.txt")
        
        if self.model_hosp:
            self.model_hosp.booster_.save_model(hosp_path)
        if self.model_icu:
            self.model_icu.booster_.save_model(icu_path)

    def load_models(self, date_str: str):
        hosp_path = os.path.join(MODEL_DIR, f"model_hosp_{date_str}.txt")
        icu_path = os.path.join(MODEL_DIR, f"model_icu_{date_str}.txt")
        
        if os.path.exists(hosp_path):
            self.model_hosp = lgb.Booster(model_file=hosp_path)
            self.explainer_hosp = shap.TreeExplainer(self.model_hosp)
        if os.path.exists(icu_path):
            self.model_icu = lgb.Booster(model_file=icu_path)
            self.explainer_icu = shap.TreeExplainer(self.model_icu)

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
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

        # Mock predictions if not trained (for testing/demo)
        if hasattr(self.model_hosp, 'predict_proba'):
            p_hosp = float(self.model_hosp.predict_proba(x_array)[0][1])
            p_icu = float(self.model_icu.predict_proba(x_array)[0][1])
            shap_vals = self.explainer_hosp.shap_values(x_array)[1][0]
        elif hasattr(self.model_hosp, 'predict'):
            # lightgbm booster predict returns proba for binary
            p_hosp = float(self.model_hosp.predict(x_array)[0])
            p_icu = float(self.model_icu.predict(x_array)[0])
            shap_vals = self.explainer_hosp.shap_values(x_array)[0]
        else:
            # mock
            p_hosp = 0.75
            p_icu = 0.35
            shap_vals = np.random.uniform(-0.5, 0.5, size=16)

        # compute top 5 shap features
        shap_abs = np.abs(shap_vals)
        top5_idx = np.argsort(shap_abs)[-5:][::-1]
        
        shap_top5 = []
        for idx in top5_idx:
            shap_top5.append({
                "feature": FEATURES[idx],
                "value": x_array[0][idx],
                "impact": float(shap_vals[idx])
            })
            
        return {
            "p_hosp_72h": p_hosp,
            "p_icu_7d": p_icu,
            "alerts": alerts,
            "shap_top5": shap_top5,
            "expected_value": float(self.explainer_hosp.expected_value[1] if hasattr(self.explainer_hosp, 'expected_value') and isinstance(self.explainer_hosp.expected_value, (list, np.ndarray)) else (self.explainer_hosp.expected_value if hasattr(self.explainer_hosp, 'expected_value') else 0)),
            "shap": shap_vals.tolist()  # For testing full sum
        }

# API Endpoint simulation logic via FastAPI router (should be integrated into epi-engine app)
from fastapi import APIRouter, HTTPException

router = APIRouter()
model_instance = DeteriorationModel()

@router.post("/api/v1/patients/{patient_id}/deterioration")
async def evaluate_deterioration(patient_id: str, payload: Dict[str, float]):
    try:
        result = model_instance.predict(payload)
        return {
            "p_hosp_72h": result["p_hosp_72h"],
            "p_icu_7d": result["p_icu_7d"],
            "alerts": result["alerts"],
            "shap_top5": result["shap_top5"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
