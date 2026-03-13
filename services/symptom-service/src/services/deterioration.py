import lightgbm as lgb
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()

class DeteriorationPredictor:
    """
    Implements the clinical deterioration prediction model (Chapter 5.2).
    Predicts hospital admission (72h) or ICU (7d) requirements.
    """
    
    FEATURES = [
        'age', 'n_comorbidities', 'days_since_onset',
        'spo2_current', 'spo2_slope_48h', 'spo2_min_24h',
        'heart_rate_current', 'hr_slope_48h',
        'fever_max_24h', 'fever_duration_h',
        'risk_score_current', 'risk_score_acceleration',
        'local_hosp_rate', 'regional_Rt'
    ]

    def __init__(self, model_hosp_path: Optional[str] = None, model_icu_path: Optional[str] = None):
        self.model_hosp = None
        self.model_icu = None
        
        if model_hosp_path:
            self.model_hosp = lgb.Booster(model_file=model_hosp_path)
        if model_icu_path:
            self.model_icu = lgb.Booster(model_file=model_icu_path)

    def predict(self, patient_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs inference for a single patient (Chapter 5.2.3).
        """
        # Convert to numpy array for fast inference
        x = np.array([[patient_features.get(f, 0.0) for f in self.FEATURES]])
        
        # Placeholder probabilities if models aren't loaded (simulates "cold start" or calibration phase)
        p_hosp = 0.05
        p_icu = 0.01
        
        if self.model_hosp:
            p_hosp = self.model_hosp.predict(x)[0]
        else:
            # Fallback algorithmic heuristic if ML model is training (Chapter 11)
            if patient_features.get('spo2_current', 100) < 92:
                p_hosp = 0.85
            elif patient_features.get('spo2_slope_48h', 0) < -2.0:
                p_hosp = 0.45

        if self.model_icu:
            p_icu = self.model_icu.predict(x)[0]

        # Generate rule-based alerts (Chapter 5.2.3)
        alerts = []
        if patient_features.get('spo2_slope_48h', 0) < -1.0 and patient_features.get('spo2_current', 100) < 95:
            alerts.append("URGENT: Falling SpO2 detected")
        
        if patient_features.get('risk_score_acceleration', 1.0) > 1.5:
            alerts.append("RAPID DETERIORATION: Risk score increased >50% in 48h")

        return {
            "p_hospitalization_72h": float(p_hosp),
            "p_icu_7d": float(p_icu),
            "alerts": alerts,
            "timestamp_utc": datetime.utcnow().isoformat()
        }

    def train(self, X_train: pd.DataFrame, y_hosp: pd.Series, y_icu: pd.Series):
        """
        Trains/Calibrates the models (Chapter 5.2.3).
        """
        logger.info("training_deterioration_model", n_samples=len(X_train))
        
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'learning_rate': 0.05,
            'num_leaves': 31,
            'class_weight': 'balanced',
            'random_state': 42,
            'verbose': -1
        }
        
        # Train Hospitalization model
        dtrain_hosp = lgb.Dataset(X_train[self.FEATURES], label=y_hosp)
        self.model_hosp = lgb.train(params, dtrain_hosp, num_boost_round=100)
        
        # Train ICU model
        dtrain_icu = lgb.Dataset(X_train[self.FEATURES], label=y_icu)
        self.model_icu = lgb.train(params, dtrain_icu, num_boost_round=100)
        
        logger.info("training_complete")
