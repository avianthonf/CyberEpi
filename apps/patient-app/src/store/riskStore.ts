import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { MMKV } from 'react-native-mmkv';
import { RiskTier } from '@/types';

interface RiskState {
  riskScore: number | null;
  riskTier: RiskTier | null;
  lastUpdated: string | null;
  recommendations: string[];
  insufficientDataMessage: string | null;
  setRiskScore: (score: number | null, tier: RiskTier | null, recommendations?: string[]) => void;
  setInsufficientData: (message: string) => void;
  clearRiskData: () => void;
}

// Use MMKV for risk score persistence (fast access)
const storage = new MMKV({
  id: 'risk-storage',
  encryptionKey: 'risk-encryption-key',
});

const mmkvStorage = {
  getItem: (name: string): string | null => {
    return storage.getString(name) ?? null;
  },
  setItem: (name: string, value: string): void => {
    storage.set(name, value);
  },
  removeItem: (name: string): void => {
    storage.delete(name);
  },
};

export const useRiskStore = create<RiskState>()(
  persist(
    (set) => ({
      // Initial state
      riskScore: null,
      riskTier: null,
      lastUpdated: null,
      recommendations: [],
      insufficientDataMessage: null,

      // Actions
      setRiskScore: (score, tier, recommendations = []) => {
        set({
          riskScore: score,
          riskTier: tier,
          lastUpdated: new Date().toISOString(),
          recommendations,
          insufficientDataMessage: null,
        });
      },

      setInsufficientData: (message) => {
        set({
          riskScore: null,
          riskTier: null,
          lastUpdated: new Date().toISOString(),
          recommendations: [],
          insufficientDataMessage: message,
        });
      },

      clearRiskData: () => {
        set({
          riskScore: null,
          riskTier: null,
          lastUpdated: null,
          recommendations: [],
          insufficientDataMessage: null,
        });
      },
    }),
    {
      name: 'risk-storage',
      storage: mmkvStorage,
    }
  )
);

// Helper function to get risk tier from score
export function getRiskTierFromScore(score: number): RiskTier {
  if (score < 0.2) return 'low';
  if (score < 0.5) return 'moderate';
  if (score < 0.75) return 'consult';
  return 'urgent';
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
