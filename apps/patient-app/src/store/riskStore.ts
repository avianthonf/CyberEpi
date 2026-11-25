import {create} from 'zustand';
import {MMKV} from 'react-native-mmkv';
import {RiskTier} from '@/types';
import {mmkv} from '@/lib/storage';
import {getPatientSession, SessionChangedError} from '@/lib/patientSession';

export interface RiskResponse {
  patient_id: string;
  risk_score: number | null;
  risk_tier: RiskTier | null;
  message?: string;
}

interface RiskSnapshot extends RiskResponse {
  lastUpdated: string | null;
  recommendations: string[];
  insufficientDataMessage: string | null;
}

interface RiskState {
  ownerId: string | null;
  riskScore: number | null;
  riskTier: RiskTier | null;
  lastUpdated: string | null;
  recommendations: string[];
  insufficientDataMessage: string | null;
  cacheError: string | null;
  bindPatient: (patientId: string | null) => void;
  setRiskScore: (
    patientId: string,
    score: number | null,
    tier: RiskTier | null,
    recommendations?: string[],
  ) => void;
  setInsufficientData: (patientId: string, message: string) => void;
}

const emptyRisk = {
  riskScore: null,
  riskTier: null,
  lastUpdated: null,
  recommendations: [] as string[],
  insufficientDataMessage: null,
};

// Read-only compatibility with the old encrypted cache. All new writes use
// the device-specific SecureStore-backed MMKV instance.
const legacyCache = new MMKV({
  id: 'risk-cache',
  encryptionKey: 'risk-cache-encryption-key',
});

function isOwnedRisk(value: unknown): value is RiskResponse {
  if (!value || typeof value !== 'object') return false;
  const record = value as Partial<RiskResponse>;
  return (
    typeof record.patient_id === 'string' &&
    /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(record.patient_id) &&
    (record.risk_score === null ||
      (typeof record.risk_score === 'number' &&
        Number.isFinite(record.risk_score) &&
        record.risk_score >= 0 &&
        record.risk_score <= 1)) &&
    (record.risk_tier === null ||
      ['low', 'moderate', 'consult', 'urgent'].includes(record.risk_tier || ''))
  );
}

function preserveOwnedLegacyRisk(record: RiskResponse, raw: string): void {
  const key = `risk_cache:${record.patient_id}:last_response`;
  const existing = mmkv.getString(key);
  if (!existing) {
    mmkv.set(key, raw);
    return;
  }
  const saved: unknown = JSON.parse(existing);
  if (!isOwnedRisk(saved) || saved.patient_id !== record.patient_id) {
    throw new Error('Existing saved risk has no matching owner. Legacy data was retained.');
  }
}

function migrateLegacyRisk(): void {
  const cached = legacyCache.getString('last_risk_response');
  if (cached) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(cached);
    } catch {
      // Unknown legacy data stays quarantined in its original store.
    }
    if (isOwnedRisk(parsed)) {
      preserveOwnedLegacyRisk(parsed, cached);
      legacyCache.delete('last_risk_response');
    }
  }

  const persisted = mmkv.getString('risk-storage');
  if (!persisted) return;
  let legacy: {state?: Record<string, unknown>};
  try {
    legacy = JSON.parse(persisted);
  } catch {
    return;
  }
  const state = legacy?.state;
  if (!state) return;
  const owned = {
    patient_id: state.ownerId || state.patient_id,
    risk_score: state.riskScore,
    risk_tier: state.riskTier,
    lastUpdated: state.lastUpdated,
    recommendations: state.recommendations,
    insufficientDataMessage: state.insufficientDataMessage,
  };
  // The historical ownerless Zustand snapshot must never be assigned to the
  // next patient. Keep it unchanged for recovery rather than deleting it.
  if (isOwnedRisk(owned)) {
    preserveOwnedLegacyRisk(owned, JSON.stringify(owned));
    mmkv.delete('risk-storage');
  }
}

export const useRiskStore = create<RiskState>((set, get) => ({
  ownerId: null,
  ...emptyRisk,
  cacheError: null,

  bindPatient: patientId => {
    // Visible state is never hydrated globally. Clear it synchronously even if
    // reading/migrating this patient's cache fails.
    set({ownerId: patientId, ...emptyRisk, cacheError: null});
    if (!patientId) return;
    try {
      migrateLegacyRisk();
    } catch {
      set({cacheError: 'Legacy risk migration could not finish. Existing records were retained.'});
    }
    try {
      const raw = mmkv.getString(`risk_cache:${patientId}:last_response`);
      if (!raw) return;
      const cached: RiskSnapshot = JSON.parse(raw);
      if (!isOwnedRisk(cached) || cached.patient_id !== patientId) {
        throw new Error('Saved risk data has no matching patient owner.');
      }
      set({
        riskScore: cached.risk_score,
        riskTier: cached.risk_tier,
        lastUpdated:
          typeof cached.lastUpdated === 'string' &&
          Number.isFinite(Date.parse(cached.lastUpdated)) ? cached.lastUpdated : null,
        recommendations: Array.isArray(cached.recommendations)
          ? cached.recommendations.filter(item => typeof item === 'string')
          : [],
        insufficientDataMessage:
          cached.risk_score === null
            ? (typeof cached.insufficientDataMessage === 'string' && cached.insufficientDataMessage) ||
              (typeof cached.message === 'string' && cached.message) ||
              'Insufficient data: Need at least 3 symptom reports'
            : null,
      });
    } catch {
      set({cacheError: 'Saved risk data could not be loaded. It has not been removed.'});
    }
  },

  setRiskScore: (patientId, score, tier, recommendations = []) => {
    if (get().ownerId !== patientId || getPatientSession().patientId !== patientId) {
      throw new SessionChangedError();
    }
    const lastUpdated = new Date().toISOString();
    const snapshot: RiskSnapshot = {
      patient_id: patientId,
      risk_score: score,
      risk_tier: tier,
      lastUpdated,
      recommendations,
      insufficientDataMessage: null,
    };
    mmkv.set(`risk_cache:${patientId}:last_response`, JSON.stringify(snapshot));
    set({
      riskScore: score,
      riskTier: tier,
      lastUpdated,
      recommendations,
      insufficientDataMessage: null,
      cacheError: null,
    });
  },

  setInsufficientData: (patientId, message) => {
    if (get().ownerId !== patientId || getPatientSession().patientId !== patientId) {
      throw new SessionChangedError();
    }
    const lastUpdated = new Date().toISOString();
    const snapshot: RiskSnapshot = {
      patient_id: patientId,
      risk_score: null,
      risk_tier: null,
      lastUpdated,
      recommendations: [],
      insufficientDataMessage: message,
    };
    mmkv.set(`risk_cache:${patientId}:last_response`, JSON.stringify(snapshot));
    set({...emptyRisk, lastUpdated, insufficientDataMessage: message, cacheError: null});
  },
}));

// Helper function to get risk tier from score
// Backend thresholds: services/symptom-service/src/services/risk.py RISK_THRESHOLDS
// [(0.8, "urgent"), (0.6, "consult"), (0.3, "moderate"), (0.0, "low")]
export function getRiskTierFromScore(score: number): RiskTier {
  if (score >= 0.8) return 'urgent';
  if (score >= 0.6) return 'consult';
  if (score >= 0.3) return 'moderate';
  return 'low';
}

// Helper function to get risk tier color
export function getRiskTierColor(tier: RiskTier | null): string {
  switch (tier) {
    case 'low':
      return '#10b981'; // green-500
    case 'moderate':
      return '#f59e0b'; // amber-500
    case 'consult':
      return '#f97316'; // orange-500
    case 'urgent':
      return '#ef4444'; // red-500
    default:
      return '#9ca3af'; // gray-400
  }
}

// Helper function to get risk tier label
export function getRiskTierLabel(tier: RiskTier | null): string {
  switch (tier) {
    case 'low':
      return 'Low Risk';
    case 'moderate':
      return 'Moderate Risk';
    case 'consult':
      return 'Consult Physician';
    case 'urgent':
      return 'Urgent - Call Now';
    default:
      return 'No Data';
  }
}
