export interface SymptomReport {
  patient_id: string; // UUID v4
  timestamp_utc: string; // ISO-8601 UTC
  reported_at_tz: string; // IANA timezone string
  fever_celsius: number | null; // 35.0-42.0 or null if not measured
  cough_severity: 0 | 1 | 2 | 3;
  dyspnoea: boolean;
  fatigue_severity: 0 | 1 | 2 | 3;
  spo2_pct: number | null; // 85-100 or null
  heart_rate_bpm: number | null;
  sore_throat: boolean;
  diarrhoea: boolean;
  anosmia: boolean;
  hrv_rmssd_ms: number | null; // from wearable
  resting_hr_bpm: number | null;
  sleep_hours: number | null;
  step_count: number | null;
  schema_version: '1.0';
}

export interface SymptomResponse {
  risk_score: number | null; // 0.0-1.0 or null if insufficient data
  risk_tier: 'low' | 'moderate' | 'consult' | 'urgent' | null;
  recommendations: string[];
  message?: string; // e.g., "Insufficient data: need at least 3 reports"
}

export interface WearableData {
  hrv_rmssd_ms: number | null;
  resting_hr_bpm: number | null;
  sleep_hours: number | null;
  step_count: number | null;
  spo2_pct: number | null;
  heart_rate_bpm: number | null;
  last_updated: string; // ISO-8601 UTC
}

export type RiskTier = 'low' | 'moderate' | 'consult' | 'urgent';

export interface RiskThresholds {
  low: [number, number]; // [0, 0.2)
  moderate: [number, number]; // [0.2, 0.5)
  consult: [number, number]; // [0.5, 0.75)
  urgent: [number, number]; // [0.75, 1.0]
}
