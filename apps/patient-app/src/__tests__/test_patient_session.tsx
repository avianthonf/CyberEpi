import React from 'react';
import {Text} from 'react-native';
import {act, render, renderHook, waitFor} from '@testing-library/react-native';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {MMKV} from 'react-native-mmkv';
import * as SecureStore from 'expo-secure-store';
import {authService} from '@/services/auth';
import {apiClient} from '@/services/api';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {useMedicationStore} from '@/store/medicationStore';
import {useRiskScore} from '@/hooks/useRiskScore';
import {mmkv} from '@/lib/storage';
import {AuthTokens, Medication, UserProfile} from '@/types';

jest.mock('@/lib/storage', () => {
  const values = new Map<string, string>();
  return {values, mmkv: {
    getString: jest.fn((key: string) => values.get(key)),
    set: jest.fn((key: string, value: string) => { values.set(key, value); }),
    delete: jest.fn((key: string) => { values.delete(key); }),
  }};
});
jest.mock('react-native-mmkv', () => {
  const stores = new Map<string, Map<string, string>>();
  return {stores, MMKV: jest.fn().mockImplementation(({id}: {id: string}) => {
    if (!stores.has(id)) stores.set(id, new Map());
    const values = stores.get(id)!;
    return {
      getString: jest.fn((key: string) => values.get(key)),
      set: jest.fn((key: string, value: string) => { values.set(key, value); }),
      delete: jest.fn((key: string) => { values.delete(key); }),
    };
  })};
});
jest.mock('expo-secure-store', () => {
  const values = new Map<string, string>();
  return {values,
    getItemAsync: jest.fn(async (key: string) => values.get(key) || null),
    setItemAsync: jest.fn(async (key: string, value: string) => { values.set(key, value); }),
    deleteItemAsync: jest.fn(async (key: string) => { values.delete(key); }),
  };
});
jest.mock('@/services/auth', () => ({authService: {
  login: jest.fn(), logout: jest.fn(), getStoredTokens: jest.fn(),
  getUserProfile: jest.fn(), refreshAccessToken: jest.fn(),
}}));
jest.mock('@/services/api', () => ({apiClient: {get: jest.fn(), post: jest.fn()}}));

const auth = jest.mocked(authService);
const api = {get: apiClient.get as jest.Mock, post: apiClient.post as jest.Mock};
const values: Map<string, string> = jest.requireMock('@/lib/storage').values;
const legacyStores: Map<string, Map<string, string>> = jest.requireMock('react-native-mmkv').stores;
const secureValues: Map<string, string> = jest.requireMock('expo-secure-store').values;
const patientA = user('patient-a');
const patientB = user('patient-b');

function user(id: string): UserProfile {
  return {id, email: `${id}@example.test`, name: id, role: 'patient',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z'};
}
function tokens(id: string): AuthTokens {
  return {access_token: `access-${id}`, refresh_token: `refresh-${id}`,
    expires_in: 3600, token_type: 'Bearer'};
}
function medication(id: string): Medication {
  return {id: `med-${id}`, patient_id: id, drug_name: `Local medicine ${id}`,
    is_active: true, adherence_rate: 80,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z'};
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return {promise, resolve};
}
function wrapper() {
  const client = new QueryClient({defaultOptions: {
    queries: {retry: false, retryDelay: 0, gcTime: Infinity},
  }});
  return ({children}: {children: React.ReactNode}) =>
    <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
async function login(profile: UserProfile) {
  auth.login.mockResolvedValueOnce(tokens(profile.id));
  auth.getUserProfile.mockResolvedValueOnce(profile);
  await act(async () => { await useAuthStore.getState().login(); });
}

beforeEach(async () => {
  jest.clearAllMocks();
  auth.logout.mockResolvedValue(undefined);
  await useAuthStore.getState().logout();
  values.clear();
  secureValues.clear();
  for (const store of legacyStores.values()) store.clear();
  api.get.mockRejectedValue(new Error('Backend temporarily unavailable'));
});

it.each(['login', 'checkAuth', 'setUser'] as const)(
  '%s selects B health state before the first B render and restores A on return', async transition => {
    await login(patientA);
    act(() => {
      useRiskStore.getState().setRiskScore(patientA.id, 0.7, 'consult');
      useMedicationStore.getState().addMedication(patientA.id, medication(patientA.id));
    });
    const seen: {id: string | null; score: number | null; owners: string[]}[] = [];
    function HealthConsumer() {
      const session = useAuthStore();
      const risk = useRiskScore(0);
      const medications = useMedicationStore(state => state.medications);
      seen.push({id: session.isAuthenticated ? session.user?.id || null : null,
        score: risk.riskScore, owners: medications.map(item => item.patient_id)});
      return <Text>{`${session.user?.id || 'signed-out'}:${risk.riskScore}:${medications.length}`}</Text>;
    }
    render(<HealthConsumer />, {wrapper: wrapper()});
    if (transition === 'login') {
      await login(patientB);
    } else if (transition === 'checkAuth') {
      auth.getStoredTokens.mockResolvedValueOnce(tokens(patientB.id));
      auth.getUserProfile.mockResolvedValueOnce(patientB);
      await act(async () => { await useAuthStore.getState().checkAuth(); });
    } else {
      act(() => { useAuthStore.getState().setUser(patientB); });
    }
    const framesB = seen.filter(frame => frame.id === patientB.id);
    expect(framesB.length).toBeGreaterThan(0);
    expect(framesB.every(frame => frame.score === null && frame.owners.length === 0)).toBe(true);
    expect(useMedicationStore.getState().medications).toEqual([]);
    expect(useRiskStore.getState().riskScore).toBeNull();

    await act(async () => { await useAuthStore.getState().logout(); });
    await login(patientA);
    expect(useRiskStore.getState().riskScore).toBe(0.7);
    expect(useMedicationStore.getState().medications).toEqual([medication(patientA.id)]);
  },
);

it('does not apply an in-flight A risk response after B becomes active', async () => {
  await login(patientA);
  const old = deferred<{data: {patient_id: string; risk_score: number; risk_tier: 'urgent'}; status: number}>();
  api.get.mockImplementation((url: string) => url.includes(patientA.id) ? old.promise :
    Promise.resolve({data: {patient_id: patientB.id, risk_score: 0.2, risk_tier: 'low'}, status: 200}));
  const {result} = renderHook(() => useRiskScore(0), {wrapper: wrapper()});
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  await login(patientB);
  await waitFor(() => expect(result.current.riskScore).toBe(0.2));
  await act(async () => {
    old.resolve({data: {patient_id: patientA.id, risk_score: 0.9, risk_tier: 'urgent'}, status: 200});
    await old.promise;
  });
  expect(result.current.riskScore).toBe(0.2);
  expect(useRiskStore.getState().ownerId).toBe(patientB.id);
  expect(JSON.parse(mmkv.getString(`risk_cache:${patientB.id}:last_response`)!)).toMatchObject({
    patient_id: patientB.id, risk_score: 0.2,
  });
});

it('retains same-owner stale risk with an honest backend error', async () => {
  await login(patientA);
  act(() => { useRiskStore.getState().setRiskScore(patientA.id, 0.4, 'moderate'); });
  const {result} = renderHook(() => useRiskScore(0), {wrapper: wrapper()});
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.riskScore).toBe(0.4);
  expect(result.current.error?.message).toContain('temporarily unavailable');
});

it('hydrates an old profile without exposing its ownerless health data to a fresh B session', async () => {
  const unknownRisk = JSON.stringify({state: {riskScore: 0.95, riskTier: 'urgent'}});
  mmkv.set('risk-storage', unknownRisk);
  await SecureStore.setItemAsync('auth-storage', JSON.stringify({state: {
    user: patientA, isAuthenticated: true,
  }, version: 0}));
  await act(async () => { await useAuthStore.persist.rehydrate(); });
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
  expect(useRiskStore.getState().riskScore).toBeNull();
  auth.getStoredTokens.mockResolvedValueOnce(tokens(patientB.id));
  auth.getUserProfile.mockResolvedValueOnce(patientB);
  await act(async () => { await useAuthStore.getState().checkAuth(); });
  expect(useAuthStore.getState().user?.id).toBe(patientB.id);
  expect(useRiskStore.getState().riskScore).toBeNull();
  expect(mmkv.getString('risk-storage')).toBe(unknownRisk);
});

it('migrates owner-tagged legacy A risk to A even when B signs in, retaining unknown legacy data', async () => {
  const legacy = new MMKV({id: 'risk-cache'});
  legacy.set('last_risk_response', JSON.stringify({patient_id: patientA.id,
    risk_score: 0.6, risk_tier: 'consult'}));
  const unknown = JSON.stringify({state: {riskScore: 0.9, riskTier: 'urgent'}});
  mmkv.set('risk-storage', unknown);
  await login(patientB);
  expect(useRiskStore.getState().riskScore).toBeNull();
  expect(JSON.parse(mmkv.getString(`risk_cache:${patientA.id}:last_response`)!)).toMatchObject({
    patient_id: patientA.id, risk_score: 0.6,
  });
  expect(mmkv.getString('risk-storage')).toBe(unknown);
  await login(patientA);
  expect(useRiskStore.getState().riskScore).toBe(0.6);
});

it('partitions legacy medications by their actual owners and quarantines unowned records', async () => {
  const unowned = {id: 'old-unowned', drug_name: 'Unassigned local record'};
  mmkv.set('medication-storage', JSON.stringify({state: {
    medications: [medication(patientA.id), unowned], activeMedications: [],
  }}));
  await login(patientB);
  expect(useMedicationStore.getState().medications).toEqual([]);
  const remaining = JSON.parse(mmkv.getString('medication-storage')!);
  expect(remaining.state.medications).toEqual([unowned]);
  await login(patientA);
  expect(useMedicationStore.getState().medications).toEqual([medication(patientA.id)]);
});

it('hides health state immediately while remote logout is still pending, without deleting records', async () => {
  await login(patientA);
  act(() => {
    useRiskStore.getState().setRiskScore(patientA.id, 0.5, 'moderate');
    useMedicationStore.getState().addMedication(patientA.id, medication(patientA.id));
  });
  const pending = deferred<void>();
  auth.logout.mockReturnValueOnce(pending.promise);
  let signingOut!: Promise<void>;
  act(() => { signingOut = useAuthStore.getState().logout(); });
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
  expect(useRiskStore.getState().riskScore).toBeNull();
  expect(useMedicationStore.getState().medications).toEqual([]);
  expect(JSON.parse(mmkv.getString(`medications:${patientA.id}`)!)).toHaveLength(1);
  await act(async () => { pending.resolve(); await signingOut; });
});
