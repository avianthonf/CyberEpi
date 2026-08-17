export interface MedicationScanRequest {
  ocr_text: string; // OCR text from the medication label
  patient_id?: string;
}

export interface MedicationScanResponse {
  drug_name: string | null;
  ndc_code: string | null;
  rxnorm_id: string | null;
  interactions: DrugInteraction[];
}

export interface DrugInteraction {
  severity: string; // e.g. 'high' | 'moderate' | 'low'
  description: string;
  drug_a: string;
  drug_b: string;
  drug_b_name?: string;
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

export interface Medication {
  id: string;
  patient_id: string;
  drug_name: string;
  dosage_form?: string;
  strength?: string;
  schedule?: MedicationSchedule;
  adherence_rate: number; // 0-100
  last_taken?: string; // ISO-8601 UTC
  next_dose?: string; // ISO-8601 UTC
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
