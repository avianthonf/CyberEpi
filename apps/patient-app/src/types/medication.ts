export interface MedicationScanRequest {
  ndc_code?: string; // National Drug Code format: XXXXX-XXXX-XX
  raw_text?: string; // OCR text if NDC not found
  patient_id: string;
}

export interface MedicationScanResponse {
  id: string; // UUID v4
  drug_name: string;
  generic_name?: string;
  brand_name?: string;
  dosage_form: string; // e.g., "tablet", "capsule", "liquid"
  strength: string; // e.g., "10mg", "500mg"
  ndc_code?: string;
  interactions: DrugInteraction[];
  schedule: MedicationSchedule;
  warnings: MedicationWarning[];
  created_at: string; // ISO-8601 UTC
}

export interface DrugInteraction {
  interacting_drug: string;
  severity: 'moderate' | 'severe' | 'contraindicated';
  description: string;
  recommendation: string;
}

export interface MedicationSchedule {
  frequency: string; // e.g., "twice daily", "once daily"
  timing: string[]; // e.g., ["morning", "evening"]
  with_food: boolean;
  reminders: {
    enabled: boolean;
    times: string[]; // HH:MM format
    sound: string;
  };
}

export interface MedicationWarning {
  type: 'allergy' | 'contraindication' | 'precaution' | 'side_effect';
  message: string;
  severity: 'info' | 'warning' | 'error';
}

export interface Medication {
  id: string;
  patient_id: string;
  drug_name: string;
  dosage_form: string;
  strength: string;
  schedule: MedicationSchedule;
  adherence_rate: number; // 0-100
  last_taken?: string; // ISO-8601 UTC
  next_dose?: string; // ISO-8601 UTC
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
