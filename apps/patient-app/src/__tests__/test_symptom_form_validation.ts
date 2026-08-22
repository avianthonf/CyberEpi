import {SymptomReport} from '@/types/symptom';
import {
  getRiskTierFromScore,
  getRiskTierColor,
  getRiskTierLabel,
} from '@/store/riskStore';

describe('Symptom Report Contract', () => {
  const createValidReport = (): SymptomReport => ({
    patient_id: '123e4567-e89b-12d3-a456-426614174000',
    symptoms: ['fever', 'cough'],
    heart_rate: 72,
    spo2: 98,
    temperature: 37.5,
  });

  describe('Required Fields', () => {
    it('has patient_id and a non-empty symptoms list', () => {
      const report = createValidReport();
      expect(typeof report.patient_id).toBe('string');
      expect(report.patient_id).toBeTruthy();
      expect(report.symptoms.length).toBeGreaterThan(0);
    });

    it('accepts an empty symptoms list (backend handles insufficient data)', () => {
      const report: SymptomReport = {
        patient_id: '123e4567-e89b-12d3-a456-426614174000',
        symptoms: [],
      };
      expect(report.symptoms).toEqual([]);
    });
  });

  describe('Vitals Ranges', () => {
    it('keeps temperature within a plausible body range', () => {
      const report = createValidReport();
      expect(report.temperature).not.toBeNull();
      if (report.temperature !== null && report.temperature !== undefined) {
        expect(report.temperature).toBeGreaterThanOrEqual(30);
        expect(report.temperature).toBeLessThanOrEqual(45);
      }
    });

    it('keeps SpO2 within 0-100', () => {
      const report = createValidReport();
      expect(report.spo2).not.toBeNull();
      if (report.spo2 !== null && report.spo2 !== undefined) {
        expect(report.spo2).toBeGreaterThanOrEqual(0);
        expect(report.spo2).toBeLessThanOrEqual(100);
      }
    });

    it('keeps heart rate within a plausible range', () => {
      const report = createValidReport();
      expect(report.heart_rate).not.toBeNull();
      if (report.heart_rate !== null && report.heart_rate !== undefined) {
        expect(report.heart_rate).toBeGreaterThanOrEqual(20);
        expect(report.heart_rate).toBeLessThanOrEqual(250);
      }
    });

    it('allows vitals to be null (not measured)', () => {
      const report: SymptomReport = {
        patient_id: '123e4567-e89b-12d3-a456-426614174000',
        symptoms: ['fatigue'],
        heart_rate: null,
        spo2: null,
        temperature: null,
      };
      expect(report.heart_rate).toBeNull();
      expect(report.spo2).toBeNull();
      expect(report.temperature).toBeNull();
    });
  });

  describe('Risk Tier Mapping (riskStore)', () => {
    it('maps scores to the documented thresholds', () => {
      expect(getRiskTierFromScore(0.1)).toBe('low');
      expect(getRiskTierFromScore(0.3)).toBe('moderate');
      expect(getRiskTierFromScore(0.6)).toBe('consult');
      expect(getRiskTierFromScore(0.9)).toBe('urgent');
    });

    it('returns a color for every tier', () => {
      for (const tier of ['low', 'moderate', 'consult', 'urgent'] as const) {
        expect(getRiskTierColor(tier)).toMatch(/^#[0-9a-f]{6}$/i);
        expect(getRiskTierLabel(tier)).toBeTruthy();
      }
    });

    it('handles null tier without crashing', () => {
      expect(getRiskTierColor(null)).toBeTruthy();
      expect(getRiskTierLabel(null)).toBeTruthy();
    });
  });
});
