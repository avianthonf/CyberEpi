export interface SymptomReport {
  patient_id: string; // UUID v4
  symptoms: string[]; // e.g. ['fever', 'cough', 'dyspnoea']
  heart_rate?: number | null;
  spo2?: number | null;
  temperature?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  region_id?: string | null;
  patch_id?: string | null;
}

export interface SymptomResponse {
  patient_id: string;
  risk_score: number | null; // 0.0-1.0 or null if insufficient data
  risk_tier: 'low' | 'moderate' | 'consult' | 'urgent' | null;
  report_count: number;
  message?: string; // e.g. "Insufficient data: need at least 3 reports"
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
