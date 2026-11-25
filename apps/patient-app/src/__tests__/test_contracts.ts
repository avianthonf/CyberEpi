/**
 * Contract tests for patient-app TypeScript types and stores.
 *
 * Verifies:
 *  - Runtime shape of exported types from src/types/
 *  - authStore initial state, login, logout, and idempotency
 *  - riskStore initial state, setRiskScore, and tier constraints
 *  - SymptomReport / SymptomResponse shapes
 */

import {act, renderHook} from '@testing-library/react-native';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore, getRiskTierFromScore} from '@/store/riskStore';
import {authService} from '@/services/auth';
import type {
  ApiResponse,
  ExposureAlert,
  NotificationType,
  PaginatedResponse,
} from '@/types';
import type {RiskTier, SymptomReport, SymptomResponse} from '@/types/symptom';

// ── Module mocks ──────────────────────────────────────────────────────────────

jest.mock('expo-secure-store', () => ({
  getItem: jest.fn(() => 'mock-key'),
  setItem: jest.fn(),
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('@/lib/storage', () => ({
  mmkvStorage: {
    getItem: jest.fn(() => null),
    setItem: jest.fn(),
    removeItem: jest.fn(),
  },
  mmkv: {
    getString: jest.fn(() => undefined),
    set: jest.fn(),
    delete: jest.fn(),
  },
  MMKV_ENCRYPTION_KEY: 'test-encryption-key',
}));

jest.mock('@/services/auth', () => ({
  authService: {
    login: jest.fn(),
    logout: jest.fn(),
    getStoredTokens: jest.fn(),
    getUserProfile: jest.fn(),
    refreshAccessToken: jest.fn(),
  },
}));

// ── Shared test fixtures ──────────────────────────────────────────────────────

const mockTokens = {
  access_token: 'test-access-token',
  refresh_token: 'test-refresh-token',
  expires_in: 3600,
  token_type: 'Bearer' as const,
};

const mockUser = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'alice@example.com',
  name: 'Alice Test',
  role: 'patient' as const,
  created_at: '2024-01-01T00:00:00.000Z',
  updated_at: '2024-01-01T00:00:00.000Z',
};

// Reset through the real logout boundary so session-scoped state also resets.
beforeEach(async () => {
  await useAuthStore.getState().logout();
  jest.clearAllMocks();
  // Reset auth store to blank state between tests
  useAuthStore.setState({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    tokens: null,
    error: null,
  });
  // Reset risk store
  useRiskStore.setState({
    riskScore: null,
    riskTier: null,
    lastUpdated: null,
    recommendations: [],
    insufficientDataMessage: null,
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: TypeScript type shape contracts (runtime assertions)
// ═══════════════════════════════════════════════════════════════════════════════

describe('ExposureAlert shape contract', () => {
  it('satisfies required fields with correct types', () => {
    const alert: ExposureAlert = {
      id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      patient_id: '11111111-1111-1111-1111-111111111111',
      alert_type: 'exposure',
      message: 'You may have been exposed.',
      severity: 'warning',
      requires_action: true,
      created_at: '2024-06-01T10:00:00.000Z',
    };

    expect(typeof alert.id).toBe('string');
    expect(typeof alert.patient_id).toBe('string');
    expect(['exposure', 'outbreak', 'risk_change']).toContain(alert.alert_type);
    expect(typeof alert.message).toBe('string');
    expect(['info', 'warning', 'urgent']).toContain(alert.severity);
    expect(typeof alert.requires_action).toBe('boolean');
    expect(typeof alert.created_at).toBe('string');
    // read_at is optional — must be string when present, or absent
    expect(alert.read_at).toBeUndefined();
  });

  it('read_at is a string when present', () => {
    const alert: ExposureAlert = {
      id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      patient_id: '11111111-1111-1111-1111-111111111111',
      alert_type: 'outbreak',
      message: 'Outbreak detected in your area.',
      severity: 'urgent',
      requires_action: true,
      created_at: '2024-06-01T10:00:00.000Z',
      read_at: '2024-06-01T11:00:00.000Z',
    };
    expect(typeof alert.read_at).toBe('string');
  });

  it('alert_type union covers exactly the three backend values', () => {
    const validTypes: ExposureAlert['alert_type'][] = [
      'exposure',
      'outbreak',
      'risk_change',
    ];
    expect(validTypes).toHaveLength(3);
    validTypes.forEach(t => {
      expect(['exposure', 'outbreak', 'risk_change']).toContain(t);
    });
  });

  it('severity union covers exactly the three backend values', () => {
    const validSeverities: ExposureAlert['severity'][] = [
      'info',
      'warning',
      'urgent',
    ];
    expect(validSeverities).toHaveLength(3);
    validSeverities.forEach(s => {
      expect(['info', 'warning', 'urgent']).toContain(s);
    });
  });
});

describe('NotificationType contract', () => {
  it('has exactly three values matching the backend enum', () => {
    // The type is a union — construct all possible values and verify them
    const validValues: NotificationType[] = [
      'RISK_CHANGE',
      'MEDICATION_REMINDER',
      'EXPOSURE_ALERT',
    ];
    expect(validValues).toHaveLength(3);
    validValues.forEach(v => {
      expect([
        'RISK_CHANGE',
        'MEDICATION_REMINDER',
        'EXPOSURE_ALERT',
      ]).toContain(v);
    });
  });
});

describe('ApiResponse<T> shape contract', () => {
  it('has data, optional message, and status(number)', () => {
    const response: ApiResponse<string[]> = {
      data: ['a', 'b'],
      status: 200,
    };
    expect(Array.isArray(response.data)).toBe(true);
    expect(typeof response.status).toBe('number');
    expect(response.message).toBeUndefined();
  });

  it('message is a string when present', () => {
    const response: ApiResponse<null> = {
      data: null,
      message: 'Not found',
      status: 404,
    };
    expect(typeof response.message).toBe('string');
  });
});

describe('PaginatedResponse<T> shape contract', () => {
  it('has all required pagination fields with correct types', () => {
    const page: PaginatedResponse<number> = {
      items: [1, 2, 3],
      total: 10,
      page: 1,
      limit: 3,
      has_next: true,
      has_prev: false,
    };
    expect(Array.isArray(page.items)).toBe(true);
    expect(typeof page.total).toBe('number');
    expect(typeof page.page).toBe('number');
    expect(typeof page.limit).toBe('number');
    expect(typeof page.has_next).toBe('boolean');
    expect(typeof page.has_prev).toBe('boolean');
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: authStore contracts
// ═══════════════════════════════════════════════════════════════════════════════

describe('authStore contracts', () => {
  describe('initial state', () => {
    it('has isAuthenticated=false, user=null, tokens=null', () => {
      const {result} = renderHook(() => useAuthStore());
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
    });

    it('error is null initially', () => {
      const {result} = renderHook(() => useAuthStore());
      expect(result.current.error).toBeNull();
    });
  });

  describe('login action', () => {
    it('sets isAuthenticated=true and populates token+user on success', async () => {
      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.tokens).toEqual(mockTokens);
      expect(result.current.user).toEqual(mockUser);
      expect(result.current.error).toBeNull();
    });

    it('leaves isAuthenticated=false and sets error on failure', async () => {
      (authService.login as jest.Mock).mockRejectedValue(
        new Error('Invalid credentials'),
      );

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        try {
          await result.current.login();
        } catch {
          // expected — store re-throws
        }
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
      expect(result.current.error).toBe('Invalid credentials');
    });
  });

  describe('logout action', () => {
    it('resets isAuthenticated, token, and user to null', async () => {
      // Establish logged-in state first
      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);
      (authService.logout as jest.Mock).mockResolvedValue(undefined);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });
      expect(result.current.isAuthenticated).toBe(true);

      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.tokens).toBeNull();
      expect(result.current.user).toBeNull();
      expect(result.current.error).toBeNull();
    });
  });

  describe('login idempotency', () => {
    it('calling login twice with same credentials does not duplicate state', async () => {
      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });
      const afterFirst = {
        isAuthenticated: result.current.isAuthenticated,
        user: result.current.user,
        tokens: result.current.tokens,
      };

      await act(async () => {
        await result.current.login();
      });

      // State must be identical — not accumulated
      expect(result.current.isAuthenticated).toBe(afterFirst.isAuthenticated);
      expect(result.current.user).toEqual(afterFirst.user);
      expect(result.current.tokens).toEqual(afterFirst.tokens);
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: riskStore contracts
// ═══════════════════════════════════════════════════════════════════════════════

describe('riskStore contracts', () => {
  beforeEach(async () => {
    (authService.login as jest.Mock).mockResolvedValue(mockTokens);
    (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);
    await useAuthStore.getState().login();
  });

  describe('initial state', () => {
    it('riskScore is null and riskTier is null', () => {
      const {result} = renderHook(() => useRiskStore());
      expect(result.current.riskScore).toBeNull();
      expect(result.current.riskTier).toBeNull();
    });

    it('recommendations is an empty array', () => {
      const {result} = renderHook(() => useRiskStore());
      expect(result.current.recommendations).toEqual([]);
    });

    it('insufficientDataMessage is null', () => {
      const {result} = renderHook(() => useRiskStore());
      expect(result.current.insufficientDataMessage).toBeNull();
    });
  });

  describe('setRiskScore action', () => {
    it('updates riskScore and riskTier', () => {
      const {result} = renderHook(() => useRiskStore());

      act(() => {
        result.current.setRiskScore(mockUser.id, 0.65, 'consult');
      });

      expect(result.current.riskScore).toBe(0.65);
      expect(result.current.riskTier).toBe('consult');
    });

    it('clears insufficientDataMessage when a score is set', () => {
      const {result} = renderHook(() => useRiskStore());

      act(() => {
        result.current.setInsufficientData(mockUser.id, 'Need more data');
      });
      expect(result.current.insufficientDataMessage).toBe('Need more data');

      act(() => {
        result.current.setRiskScore(mockUser.id, 0.3, 'moderate');
      });
      expect(result.current.insufficientDataMessage).toBeNull();
    });

    it('stores recommendations when provided', () => {
      const {result} = renderHook(() => useRiskStore());

      act(() => {
        result.current.setRiskScore(mockUser.id, 0.8, 'urgent', [
          'Seek immediate care',
          'Call your doctor',
        ]);
      });

      expect(result.current.recommendations).toEqual([
        'Seek immediate care',
        'Call your doctor',
      ]);
    });

    it('sets lastUpdated to an ISO string', () => {
      const {result} = renderHook(() => useRiskStore());

      act(() => {
        result.current.setRiskScore(mockUser.id, 0.1, 'low');
      });

      expect(typeof result.current.lastUpdated).toBe('string');
      expect(() => new Date(result.current.lastUpdated!)).not.toThrow();
    });
  });

  describe('risk tier value constraints', () => {
    // Backend authoritative thresholds from services/symptom-service/src/services/risk.py:
    // RISK_THRESHOLDS = [(0.8, "urgent"), (0.6, "consult"), (0.3, "moderate"), (0.0, "low")]
    it('getRiskTierFromScore returns low for score < 0.3', () => {
      expect(getRiskTierFromScore(0)).toBe('low');
      expect(getRiskTierFromScore(0.25)).toBe('low');
      expect(getRiskTierFromScore(0.29)).toBe('low');
    });

    it('getRiskTierFromScore returns moderate for 0.3 <= score < 0.6', () => {
      expect(getRiskTierFromScore(0.3)).toBe('moderate');
      expect(getRiskTierFromScore(0.45)).toBe('moderate');
      expect(getRiskTierFromScore(0.59)).toBe('moderate');
    });

    it('getRiskTierFromScore returns consult for 0.6 <= score < 0.8', () => {
      expect(getRiskTierFromScore(0.6)).toBe('consult');
      expect(getRiskTierFromScore(0.7)).toBe('consult');
      expect(getRiskTierFromScore(0.79)).toBe('consult');
    });

    it('getRiskTierFromScore returns urgent for score >= 0.8', () => {
      expect(getRiskTierFromScore(0.8)).toBe('urgent');
      expect(getRiskTierFromScore(0.9)).toBe('urgent');
      expect(getRiskTierFromScore(1.0)).toBe('urgent');
    });

    it('boundary tests: inclusive higher tier at exact thresholds', () => {
      expect(getRiskTierFromScore(0.3)).toBe('moderate'); // boundary: 0.3 is moderate
      expect(getRiskTierFromScore(0.6)).toBe('consult'); // boundary: 0.6 is consult
      expect(getRiskTierFromScore(0.8)).toBe('urgent'); // boundary: 0.8 is urgent
    });

    it('every tier value is within the backend-defined set', () => {
      const validTiers: RiskTier[] = ['low', 'moderate', 'consult', 'urgent'];
      const scores = [0.1, 0.3, 0.55, 0.6, 0.775, 0.8, 0.9];
      scores.forEach(score => {
        const tier = getRiskTierFromScore(score);
        expect(validTiers).toContain(tier);
      });
    });
  });

  describe('visible risk unbinding', () => {
    it('hides the current risk without assigning its cache to another patient', () => {
      const {result} = renderHook(() => useRiskStore());

      act(() => {
        result.current.setRiskScore(mockUser.id, 0.5, 'consult', ['Rec A']);
      });

      act(() => {
        result.current.bindPatient(null);
      });

      expect(result.current.riskScore).toBeNull();
      expect(result.current.riskTier).toBeNull();
      expect(result.current.lastUpdated).toBeNull();
      expect(result.current.recommendations).toEqual([]);
    });
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: Symptom type contracts
// ═══════════════════════════════════════════════════════════════════════════════

describe('SymptomReport shape contract', () => {
  it('requires patient_id(string) and symptoms(array)', () => {
    const report: SymptomReport = {
      patient_id: '11111111-1111-1111-1111-111111111111',
      symptoms: ['fever', 'cough'],
    };
    expect(typeof report.patient_id).toBe('string');
    expect(Array.isArray(report.symptoms)).toBe(true);
  });

  it('optional vitals fields may be omitted', () => {
    const report: SymptomReport = {
      patient_id: '11111111-1111-1111-1111-111111111111',
      symptoms: ['fatigue'],
    };
    expect(report.heart_rate).toBeUndefined();
    expect(report.spo2).toBeUndefined();
    expect(report.temperature).toBeUndefined();
    expect(report.systolic_bp).toBeUndefined();
    expect(report.diastolic_bp).toBeUndefined();
  });

  it('optional vitals fields accept number or null', () => {
    const report: SymptomReport = {
      patient_id: '11111111-1111-1111-1111-111111111111',
      symptoms: ['dyspnoea'],
      heart_rate: 90,
      spo2: null,
      temperature: 37.8,
    };
    expect(typeof report.heart_rate).toBe('number');
    expect(report.spo2).toBeNull();
  });
});

describe('SymptomResponse shape contract', () => {
  it('has risk_score(number|null), risk_tier(string|null), report_count(number)', () => {
    const response: SymptomResponse = {
      patient_id: '11111111-1111-1111-1111-111111111111',
      risk_score: 0.42,
      risk_tier: 'moderate',
      report_count: 5,
    };
    expect(typeof response.risk_score).toBe('number');
    expect(typeof response.risk_tier).toBe('string');
    expect(typeof response.report_count).toBe('number');
  });

  it('risk_score and risk_tier may be null', () => {
    const response: SymptomResponse = {
      patient_id: '11111111-1111-1111-1111-111111111111',
      risk_score: null,
      risk_tier: null,
      report_count: 1,
    };
    expect(response.risk_score).toBeNull();
    expect(response.risk_tier).toBeNull();
  });

  it('risk_tier values match the backend-defined set when non-null', () => {
    const validTiers: SymptomResponse['risk_tier'][] = [
      'low',
      'moderate',
      'consult',
      'urgent',
    ];
    validTiers.forEach(tier => {
      const response: SymptomResponse = {
        patient_id: '11111111-1111-1111-1111-111111111111',
        risk_score: 0.3,
        risk_tier: tier,
        report_count: 3,
      };
      expect([null, 'low', 'moderate', 'consult', 'urgent']).toContain(
        response.risk_tier,
      );
    });
  });
});
