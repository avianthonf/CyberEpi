import {QueryClient, useQuery, useQueryClient} from '@tanstack/react-query';
import {useEffect} from 'react';
import NetInfo from '@react-native-community/netinfo';
import axios from 'axios';
import {apiClient} from '@/services/api';
import {useAuthStore} from '@/store/authStore';
import {RiskResponse, useRiskStore} from '@/store/riskStore';
import {RiskTier} from '@/types';
import {
  PatientSession, getPatientSession, assertPatientSession,
  isPatientSessionCurrent, SessionChangedError,
} from '@/lib/patientSession';
import {flushSymptomQueue} from '@/lib/symptomQueue';

export function useRiskScore(refreshInterval: number = 5 * 60 * 1000) {
  const {user, isAuthenticated, sessionGeneration} = useAuthStore();
  const session = getPatientSession();
  const risk = useRiskStore();
  const active = isAuthenticated && !!session.patientId && session.patientId === user?.id;
  const query = useQuery({
    queryKey: ['risk-score', session.patientId, sessionGeneration],
    queryFn: async ({signal}): Promise<RiskResponse> => {
      assertPatientSession(session);
      if (!session.patientId) throw new Error('User not authenticated');
      const response = await apiClient.get<RiskResponse>(
        `/patients/${session.patientId}/risk`, undefined, {patientSession: session, signal},
      );
      assertPatientSession(session);
      const data = response.data;
      if (data.patient_id !== session.patientId) {
        throw new Error('Risk response did not match the signed-in patient.');
      }
      if (data.risk_score !== null && data.risk_tier) {
        risk.setRiskScore(session.patientId, data.risk_score, data.risk_tier);
      } else {
        risk.setInsufficientData(session.patientId,
          data.message || 'Insufficient data: Need at least 3 symptom reports');
      }
      return data;
    },
    enabled: active,
    refetchInterval: refreshInterval,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    staleTime: 2 * 60 * 1000,
    retry: (failureCount, error) => {
      if (error instanceof SessionChangedError) return false;
      if (axios.isAxiosError(error) &&
        [401, 403, 404].includes(error.response?.status || 0)) return false;
      return failureCount < 3;
    },
  });

  // Do not rely on an effect to clear old health values. This owner check also
  // covers the render between an auth update and any React effect cleanup.
  const owned = active && risk.ownerId === session.patientId;
  const lastUpdated = owned ? risk.lastUpdated : null;
  const getTimeSinceLastUpdate = (): string => {
    if (!lastUpdated) return 'Never';
    const diffMs = Date.now() - new Date(lastUpdated).getTime();
    const minutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    return `${days} day${days > 1 ? 's' : ''} ago`;
  };

  return {
    riskScore: owned ? risk.riskScore : null,
    riskTier: owned ? risk.riskTier : null,
    insufficientDataMessage: owned ? risk.insufficientDataMessage : null,
    lastUpdated,
    isLoading: active && query.isLoading,
    isError: active && (query.isError || !!risk.cacheError),
    error: active ? query.error || (risk.cacheError ? new Error(risk.cacheError) : null) : null,
    refreshRiskScore: query.refetch,
    getTimeSinceLastUpdate,
    isDataStale: () => !lastUpdated ||
      Date.now() - new Date(lastUpdated).getTime() > 10 * 60 * 1000,
  };
}

export interface RiskHistoryItem {
  time: string;
  risk_score: number | null;
  risk_tier: RiskTier | null;
  symptoms: Record<string, unknown> | unknown[] | null;
  patient_id?: string;
}

// The backend returns at most the latest 30 records and does not filter days.
// The history screen applies the selected date window to this bounded result.
export function useRiskScoreHistory(days: number = 7) {
  const {user, isAuthenticated, sessionGeneration} = useAuthStore();
  const session = getPatientSession();
  const active = isAuthenticated && !!session.patientId && session.patientId === user?.id;
  const query = useQuery({
    queryKey: ['risk-score-history', session.patientId, days, sessionGeneration],
    queryFn: async ({signal}) => {
      assertPatientSession(session);
      if (!session.patientId) throw new Error('User not authenticated');
      const response = await apiClient.get<RiskHistoryItem[]>(
        `/patients/${session.patientId}/history`, undefined, {patientSession: session, signal},
      );
      assertPatientSession(session);
      if (!Array.isArray(response.data)) throw new Error('History response was not a list.');
      // Current backend rows have no owner field; the authenticated scoped URL
      // and session guard bind them. Reject contradictory ownership if supplied.
      if (response.data.some(row => row && typeof row === 'object' &&
        'patient_id' in row && row.patient_id !== session.patientId)) {
        throw new Error('History response did not match the signed-in patient.');
      }
      return response.data;
    },
    enabled: active,
    staleTime: 5 * 60 * 1000,
  });
  return {...query, data: active ? query.data : undefined};
}

interface NetworkSubscription {
  users: number;
  online: boolean;
  unsubscribe: () => void;
  sync: {session: PatientSession; promise: Promise<void>} | null;
}

const networkSubscriptions = new WeakMap<QueryClient, NetworkSubscription>();

export function syncPatientAfterReconnect(client: QueryClient): Promise<void> {
  const session = getPatientSession();
  if (!session.patientId) return Promise.resolve();
  const subscription = networkSubscriptions.get(client);
  if (subscription?.sync && isPatientSessionCurrent(subscription.sync.session)) {
    return subscription.sync.promise;
  }
  const promise = (async () => {
    try {
      await flushSymptomQueue(session);
    } finally {
      // Refresh even after a partial flush failure, but never under a new owner.
      if (isPatientSessionCurrent(session)) {
        await Promise.all([
          client.invalidateQueries({queryKey: ['risk-score', session.patientId]}),
          client.invalidateQueries({queryKey: ['risk-score-history', session.patientId]}),
        ]);
      }
    }
  })().finally(() => {
    if (subscription?.sync?.promise === promise) subscription.sync = null;
  });
  if (subscription) subscription.sync = {session, promise};
  return promise;
}

function startNetworkSync(client: QueryClient): void {
  const session = getPatientSession();
  void syncPatientAfterReconnect(client).catch(error => {
    if (session.patientId && isPatientSessionCurrent(session)) {
      useAuthStore.getState().setError(error instanceof Error ? error.message :
        'Pending reports could not be synced. They remain saved locally.');
    }
  });
}

export function useNetworkSync() {
  const client = useQueryClient();
  const generation = useAuthStore(state => state.sessionGeneration);

  useEffect(() => {
    let subscription = networkSubscriptions.get(client);
    if (!subscription) {
      const entry: NetworkSubscription = {
        users: 0, online: false, unsubscribe: () => {}, sync: null,
      };
      networkSubscriptions.set(client, entry);
      entry.unsubscribe = NetInfo.addEventListener(state => {
        const online = state.isConnected === true && state.isInternetReachable !== false;
        const restored = online && !entry.online;
        entry.online = online;
        if (restored) startNetworkSync(client);
      });
      subscription = entry;
    }
    const activeSubscription = subscription;
    ++activeSubscription.users;
    return () => {
      if (--activeSubscription.users === 0) {
        activeSubscription.unsubscribe();
        networkSubscriptions.delete(client);
      }
    };
  }, [client]);

  useEffect(() => {
    if (networkSubscriptions.get(client)?.online) startNetworkSync(client);
  }, [client, generation]);
}
