import { MedScannerService } from '@/services/medScanner';

describe('Medication Scanner', () => {
  let scanner: MedScannerService;

  beforeEach(() => {
    scanner = MedScannerService.getInstance();
  });

  describe('NDC Code Extraction', () => {
    it('should extract valid NDC code in standard format', () => {
      const text = 'NDC: 12345-6789-01\nLisinopril 10mg Tablets';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBe('12345-6789-01');
    });

    it('should extract NDC code without dashes', () => {
      const text = 'NDC 12345678901 Metformin 500mg';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBe('12345-6789-01');
    });

    it('should extract NDC code with prefix label', () => {
      const text = 'National Drug Code NDC: 54321-0987-65 Aspirin';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBe('54321-0987-65');
    });

    it('should extract first NDC code when multiple are present', () => {
      const text = 'NDC: 11111-2222-33 and NDC: 44444-5555-66';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBe('11111-2222-33');
    });

    it('should return null when no NDC code is found', () => {
      const text = 'Aspirin 81mg Enteric Coated Tablets';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBeNull();
    });

    it('should return null for partial NDC codes', () => {
      const text = 'NDC: 12345-6789';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBeNull();
    });

    it('should return null for NDC with wrong digit counts', () => {
      const text = 'NDC: 1234-56789-01';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBeNull();
    });

    it('should handle noisy OCR text with valid NDC', () => {
      const text = 'Rx Only\n\nNDC  98765-4321-09\n\nStore at 20-25°C';
      const ndc = scanner.extractNDCCode(text);
      expect(ndc).toBe('98765-4321-09');
    });
  });

  describe('Drug Name Extraction', () => {
    it('should extract drug name with dosage', () => {
      const text = 'Lisinopril 10mg Tablets';
      const name = scanner.extractDrugName(text);
      expect(name).toBe('Lisinopril');
    });

    it('should extract multi-word drug names', () => {
      const text = 'Atorvastatin Calcium 20mg Tablets';
      const name = scanner.extractDrugName(text);
      expect(name).toBe('Atorvastatin Calcium');
    });

    it('should return null when no drug name pattern matches', () => {
      const text = 'Take with food. Store at room temperature.';
      const name = scanner.extractDrugName(text);
      expect(name).toBeNull();
    });
  });

  describe('Severe Interaction Detection', () => {
    it('should detect severe interactions', () => {
      const medication = {
        drug_name: 'TestDrug',
        ndc_code: '12345-6789-01',
        rxnorm_id: '123',
        interactions: [
          {
            drug_a: '123',
            drug_b: '456',
            severity: 'severe' as const,
            description: 'Severe interaction detected',
          },
        ],
      };

      expect(scanner.hasSevereInteractions(medication)).toBe(true);
    });

    it('should detect contraindicated interactions', () => {
      const medication = {
        drug_name: 'TestDrug',
        ndc_code: '12345-6789-01',
        rxnorm_id: '123',
        interactions: [
          {
            drug_a: '123',
            drug_b: '456',
            severity: 'contraindicated' as const,
            description: 'Contraindicated combination',
          },
        ],
      };

      expect(scanner.hasSevereInteractions(medication)).toBe(true);
    });

    it('should return false for moderate-only interactions', () => {
      const medication = {
        drug_name: 'TestDrug',
        ndc_code: '12345-6789-01',
        rxnorm_id: '123',
        interactions: [
          {
            drug_a: '123',
            drug_b: '456',
            severity: 'moderate' as const,
            description: 'Moderate interaction',
          },
        ],
      };

      expect(scanner.hasSevereInteractions(medication)).toBe(false);
    });

    it('should return false for no interactions', () => {
      const medication = {
        drug_name: 'TestDrug',
        ndc_code: '12345-6789-01',
        rxnorm_id: '123',
        interactions: [],
      };

      expect(scanner.hasSevereInteractions(medication)).toBe(false);
    });
  });

  describe('Interaction Severity Colors', () => {
    it('should return amber for moderate severity', () => {
      expect(scanner.getInteractionSeverityColor('moderate')).toBe('#f59e0b');
    });

    it('should return orange for severe severity', () => {
      expect(scanner.getInteractionSeverityColor('severe')).toBe('#f97316');
    });

    it('should return red for contraindicated severity', () => {
      expect(scanner.getInteractionSeverityColor('contraindicated')).toBe('#dc2626');
    });

    it('should return gray for unknown severity', () => {
      expect(scanner.getInteractionSeverityColor('unknown')).toBe('#6b7280');
    });
  });
});
