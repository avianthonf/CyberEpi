export * from './symptom';
export * from './auth';
export * from './medication';

export interface ApiResponse<T = any> {
  data: T;
  message?: string;
  status: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ExposureAlert {
  id: string;
  patient_id: string;
  alert_type: 'exposure' | 'outbreak' | 'risk_change';
  message: string;
  severity: 'info' | 'warning' | 'urgent';
  requires_action: boolean;
  created_at: string;
  read_at?: string;
}

export type NotificationType = 'RISK_CHANGE' | 'MEDICATION_REMINDER' | 'EXPOSURE_ALERT';
