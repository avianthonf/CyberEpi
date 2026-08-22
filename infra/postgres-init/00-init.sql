-- Create user and database
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'cyberepi') THEN
      CREATE USER cyberepi WITH PASSWORD 'devpassword';
   END IF;
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cyberepi') THEN
      CREATE DATABASE cyberepi;
   END IF;
END
$do$;
GRANT ALL PRIVILEGES ON DATABASE cyberepi TO cyberepi;

-- CyberEpi – Idempotent Database Initialization
-- Runs on first postgres startup via docker-entrypoint-initdb.d
-- Covers ALL component schemas (01–08)

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Also create keycloak database for Keycloak service
SELECT 'CREATE DATABASE keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

-- ═══════════════════════════════════════════
-- Component 01: Epidemiological Parameters
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS epi_params (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    disease VARCHAR(50) NOT NULL DEFAULT 'influenza',
    beta FLOAT NOT NULL,
    sigma FLOAT NOT NULL,
    gamma FLOAT NOT NULL,
    mu FLOAT,
    R0 FLOAT,
    source VARCHAR(100),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (region_id, disease, valid_from)
);

CREATE TABLE IF NOT EXISTS forecast_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    disease VARCHAR(50) NOT NULL DEFAULT 'influenza',
    horizon_days INT NOT NULL,
    forecast_data JSONB NOT NULL,
    model_version VARCHAR(50),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forecast_cache_region ON forecast_cache(region_id, disease, computed_at DESC);

-- ═══════════════════════════════════════════
-- Component 02: Filter History (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS filter_history (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    disease VARCHAR(50) NOT NULL DEFAULT 'influenza',
    state JSONB NOT NULL,
    covariance JSONB,
    log_likelihood FLOAT,
    filter_type VARCHAR(30) NOT NULL DEFAULT 'EKF',
    innovation JSONB
);

SELECT create_hypertable('filter_history', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_filter_history_region ON filter_history(region_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 03/08: Clinical – Patients
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keycloak_id VARCHAR(100) UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    date_of_birth DATE,
    gender VARCHAR(20),
    region_id VARCHAR(50),
    patch_id VARCHAR(20),
    email VARCHAR(200),
    phone VARCHAR(30),
    risk_tier VARCHAR(20) DEFAULT 'low',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patients_region ON patients(region_id);
CREATE INDEX IF NOT EXISTS idx_patients_keycloak ON patients(keycloak_id);

-- ═══════════════════════════════════════════
-- Component 03/08: Clinical – Prescriptions
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS prescriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    physician_id UUID,
    drug_name VARCHAR(200) NOT NULL,
    ndc_code VARCHAR(50),
    rxnorm_id VARCHAR(50),
    dosage VARCHAR(100),
    frequency VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL,
    end_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id, status);

-- ═══════════════════════════════════════════
-- Component 03/08: Clinical – Adherence Events
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS adherence_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prescription_id UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    method VARCHAR(30) DEFAULT 'manual',
    confirmed BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_adherence_patient ON adherence_events(patient_id, taken_at DESC);

-- ═══════════════════════════════════════════
-- Component 03/08: Clinical – Vitals (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vitals_ts (
    time TIMESTAMPTZ NOT NULL,
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    heart_rate INT,
    spo2 FLOAT,
    temperature FLOAT,
    systolic_bp INT,
    diastolic_bp INT,
    symptoms JSONB,
    risk_score FLOAT,
    risk_tier VARCHAR(20),
    source VARCHAR(30) DEFAULT 'app'
);

SELECT create_hypertable('vitals_ts', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_vitals_patient ON vitals_ts(patient_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 05: Spatial – States (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS spatial_states (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20) NOT NULL,
    S FLOAT NOT NULL,
    E FLOAT,
    I FLOAT NOT NULL,
    R FLOAT NOT NULL,
    H FLOAT,
    D FLOAT,
    N FLOAT NOT NULL,
    Rt FLOAT
);

SELECT create_hypertable('spatial_states', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_spatial_region_patch ON spatial_states(region_id, patch_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 05: Spatial – Rt Estimates (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS rt_estimates (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20),
    Rt FLOAT NOT NULL,
    Rt_lower FLOAT,
    Rt_upper FLOAT,
    method VARCHAR(30) DEFAULT 'EKF'
);

SELECT create_hypertable('rt_estimates', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_rt_region ON rt_estimates(region_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 05: Spatial – Mobility Matrix
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mobility_matrix (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    from_patch VARCHAR(20) NOT NULL,
    to_patch VARCHAR(20) NOT NULL,
    flow_weight FLOAT NOT NULL DEFAULT 0.0,
    source VARCHAR(50),
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    UNIQUE (region_id, from_patch, to_patch, valid_from)
);

-- ═══════════════════════════════════════════
-- Component 06: Control Weights & Recommendations
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS control_weights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    w_economic FLOAT NOT NULL DEFAULT 0.33,
    w_health FLOAT NOT NULL DEFAULT 0.34,
    w_social FLOAT NOT NULL DEFAULT 0.33,
    set_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20),
    recommendation JSONB NOT NULL,
    Rt_at_decision FLOAT,
    cost_value FLOAT,
    status VARCHAR(30) DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_control_rec_region ON control_recommendations(region_id, created_at DESC);

-- ═══════════════════════════════════════════
-- Component 07: Privacy – FL & Budget
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS privacy_budget (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id VARCHAR(50) NOT NULL,
    epsilon_total FLOAT NOT NULL DEFAULT 0.0,
    epsilon_limit FLOAT NOT NULL DEFAULT 10.0,
    delta FLOAT NOT NULL DEFAULT 1e-5,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fl_rounds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_number INT NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    participants INT NOT NULL DEFAULT 0,
    global_loss FLOAT,
    accuracy FLOAT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(30) DEFAULT 'in_progress'
);

CREATE INDEX IF NOT EXISTS idx_fl_rounds_region ON fl_rounds(region_id, round_number DESC);

CREATE TABLE IF NOT EXISTS fl_model_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_id UUID REFERENCES fl_rounds(id),
    model_type VARCHAR(50) NOT NULL,
    version VARCHAR(30) NOT NULL,
    weights_path VARCHAR(500),
    metrics JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════
-- Component 08: Surveillance – Confirmed Cases (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS confirmed_cases (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20),
    count INT NOT NULL,
    source VARCHAR(50)
);

SELECT create_hypertable('confirmed_cases', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_confirmed_region ON confirmed_cases(region_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 08: Surveillance – Hospital Admissions (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hospital_admissions (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20),
    admissions INT NOT NULL,
    current_H INT,
    current_ICU INT,
    capacity_H INT,
    capacity_ICU INT
);

SELECT create_hypertable('hospital_admissions', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_hospital_region ON hospital_admissions(region_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 08: Surveillance – Pharmacy Signals (Hypertable)
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS pharmacy_signals (
    time TIMESTAMPTZ NOT NULL,
    region_id VARCHAR(50) NOT NULL,
    patch_id VARCHAR(20),
    otc_count INT NOT NULL,
    drug_class VARCHAR(50)
);

SELECT create_hypertable('pharmacy_signals', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_pharmacy_region ON pharmacy_signals(region_id, time DESC);

-- ═══════════════════════════════════════════
-- Component 08: Notifications – Push Tokens
-- ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS push_tokens (
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    token VARCHAR(200) NOT NULL,
    platform VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (patient_id, platform)
);

-- ═══════════════════════════════════════════
-- Grants (for dev environment)
-- ═══════════════════════════════════════════
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cyberepi;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cyberepi;
