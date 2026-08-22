import numpy as np
import pytest

from src.ml.deterioration import FEATURES, DeteriorationModel


@pytest.fixture
def model_fixture():
    model = DeteriorationModel()
    # Mocking trained model behaviour for tests
    X_train = np.random.rand(100, 16)
    y_hosp = np.random.randint(0, 2, 100)
    y_icu = np.random.randint(0, 2, 100)
    model.train(X_train, y_hosp, y_icu)
    return model

def test_feature_count_matches():
    assert len(FEATURES) == 16

def test_model_output_probability(model_fixture):
    # Dummy valid payload
    features = {f: 0.5 for f in FEATURES}
    result = model_fixture.predict(features)
    assert 0 <= result['p_hosp_72h'] <= 1
    assert 0 <= result['p_icu_7d'] <= 1

def test_shap_values_sum_to_output(model_fixture):
    features = {f: 0.5 for f in FEATURES}
    result = model_fixture.predict(features)

    pred_hosp_logit = sum(result['shap']) + result['expected_value']
    # Sigmoid function for probability
    pred_hosp_prob = 1 / (1 + np.exp(-pred_hosp_logit))
    # SHAP explainer output matches probability (or log odds, based on model)
    assert abs(pred_hosp_prob - result['p_hosp_72h']) < 1e-4

def test_alert_thresholds(model_fixture):
    features = {f: 0.5 for f in FEATURES}
    features['spo2_slope_48h'] = -1.2
    features['spo2_current'] = 94
    features['risk_score_acceleration'] = 0

    result = model_fixture.predict(features)
    assert "URGENT" in result["alerts"]
    assert "RAPID_DETERIORATION" not in result["alerts"]

    features['spo2_current'] = 96
    features['risk_score_acceleration'] = 2.0
    result2 = model_fixture.predict(features)
    assert "URGENT" not in result2["alerts"]
    assert "RAPID_DETERIORATION" in result2["alerts"]
