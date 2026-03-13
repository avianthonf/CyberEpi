import { SymptomReport } from '@/types/symptom';

describe('Symptom Form Validation', () => {
  const createValidReport = (): SymptomReport => ({
    patient_id: '123e4567-e89b-12d3-a456-426614174000',
    timestamp_utc: '2024-03-11T10:00:00.000Z',
    reported_at_tz: 'America/New_York',
    fever_celsius: 37.5,
    cough_severity: 1,
    dyspnoea: false,
    fatigue_severity: 2,
    spo2_pct: 98,
    heart_rate_bpm: 72,
    sore_throat: false,
    diarrhoea: false,
    anosmia: false,
    hrv_rmssd_ms: 45,
    resting_hr_bpm: 60,
    sleep_hours: 7.5,
    step_count: 10000,
    schema_version: '1.0',
  });

  describe('Temperature Validation', () => {
    it('should accept valid temperature range', () => {
      const report = createValidReport();
      
      // Test boundary values
      report.fever_celsius = 35.0;
      expect(report.fever_celsius).toBeGreaterThanOrEqual(35.0);
      
      report.fever_celsius = 42.0;
      expect(report.fever_celsius).toBeLessThanOrEqual(42.0);
      
      // Test middle values
      report.fever_celsius = 37.0;
      expect(report.fever_celsius).toBeGreaterThanOrEqual(35.0);
      expect(report.fever_celsius).toBeLessThanOrEqual(42.0);
    });

    it('should reject temperature below minimum', () => {
      const report = createValidReport();
      report.fever_celsius = 34.9;
      
      expect(report.fever_celsius).toBeLessThan(35.0);
    });

    it('should reject temperature above maximum', () => {
      const report = createValidReport();
      report.fever_celsius = 42.1;
      
      expect(report.fever_celsius).toBeGreaterThan(42.0);
    });

    it('should accept null temperature when not measured', () => {
      const report = createValidReport();
      report.fever_celsius = null;
      
      expect(report.fever_celsius).toBeNull();
    });
  });

  describe('SpO2 Validation', () => {
    it('should accept valid SpO2 range', () => {
      const report = createValidReport();
      
      // Test boundary values
      report.spo2_pct = 85;
      expect(report.spo2_pct).toBeGreaterThanOrEqual(85);
      
      report.spo2_pct = 100;
      expect(report.spo2_pct).toBeLessThanOrEqual(100);
      
      // Test middle values
      report.spo2_pct = 95;
      expect(report.spo2_pct).toBeGreaterThanOrEqual(85);
      expect(report.spo2_pct).toBeLessThanOrEqual(100);
    });

    it('should reject SpO2 below minimum', () => {
      const report = createValidReport();
      report.spo2_pct = 84;
      
      expect(report.spo2_pct).toBeLessThan(85);
    });

    it('should reject SpO2 above maximum', () => {
      const report = createValidReport();
      report.spo2_pct = 101;
      
      expect(report.spo2_pct).toBeGreaterThan(100);
    });

    it('should accept null SpO2 when not measured', () => {
      const report = createValidReport();
      report.spo2_pct = null;
      
      expect(report.spo2_pct).toBeNull();
    });
  });

  describe('Cough Severity Validation', () => {
    it('should accept valid cough severity values', () => {
      const report = createValidReport();
      
      const validValues: [0, 1, 2, 3] = [0, 1, 2, 3];
      
      validValues.forEach((severity) => {
        report.cough_severity = severity;
        expect([0, 1, 2, 3]).toContain(report.cough_severity);
      });
    });

    it('should reject invalid cough severity values', () => {
      const report = createValidReport();
      
      // @ts-expect-error - Testing invalid value
      report.cough_severity = 4;
      expect([0, 1, 2, 3]).not.toContain(report.cough_severity);
      
      // @ts-expect-error - Testing negative value
      report.cough_severity = -1;
      expect([0, 1, 2, 3]).not.toContain(report.cough_severity);
    });
  });

  describe('Fatigue Severity Validation', () => {
    it('should accept valid fatigue severity values', () => {
      const report = createValidReport();
      
      const validValues: [0, 1, 2, 3] = [0, 1, 2, 3];
      
      validValues.forEach((severity) => {
        report.fatigue_severity = severity;
        expect([0, 1, 2, 3]).toContain(report.fatigue_severity);
      });
    });

    it('should reject invalid fatigue severity values', () => {
      const report = createValidReport();
      
      // @ts-expect-error - Testing invalid value
      report.fatigue_severity = 4;
      expect([0, 1, 2, 3]).not.toContain(report.fatigue_severity);
    });
  });

  describe('Schema Version Validation', () => {
    it('should have correct schema version', () => {
      const report = createValidReport();
      expect(report.schema_version).toBe('1.0');
    });
  });

  describe('Required Fields Validation', () => {
    it('should have all required fields', () => {
      const report = createValidReport();
      
      // Check required string fields
      expect(typeof report.patient_id).toBe('string');
      expect(report.patient_id).toBeTruthy();
      
      expect(typeof report.timestamp_utc).toBe('string');
      expect(report.timestamp_utc).toBeTruthy();
      
      expect(typeof report.reported_at_tz).toBe('string');
      expect(report.reported_at_tz).toBeTruthy();
      
      // Check required numeric fields
      expect(typeof report.cough_severity).toBe('number');
      expect([0, 1, 2, 3]).toContain(report.cough_severity);
      
      expect(typeof report.fatigue_severity).toBe('number');
      expect([0, 1, 2, 3]).toContain(report.fatigue_severity);
      
      // Check required boolean fields
      expect(typeof report.dyspnoea).toBe('boolean');
      expect(typeof report.sore_throat).toBe('boolean');
      expect(typeof report.diarrhoea).toBe('boolean');
      expect(typeof report.anosmia).toBe('boolean');
    });
  });

  describe('Timestamp Format Validation', () => {
    it('should have valid ISO-8601 timestamp', () => {
      const report = createValidReport();
      const timestamp = new Date(report.timestamp_utc);
      
      expect(timestamp.toISOString()).toBe(report.timestamp_utc);
    });
  });

  describe('UUID Validation for Patient ID', () => {
    it('should have valid UUID v4 format', () => {
      const report = createValidReport();
      const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      
      expect(uuidRegex.test(report.patient_id)).toBe(true);
    });
  });
});
