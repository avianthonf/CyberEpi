import React from 'react';
import {act, renderHook, waitFor} from '@testing-library/react-native';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {AxiosError} from 'axios';
import {MMKV} from 'react-native-mmkv';
import NetInfo from '@react-native-community/netinfo';
import {randomUUID} from 'expo-crypto';
import {authService} from '@/services/auth';
import {apiClient} from '@/services/api';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {useSymptomSubmit} from '@/hooks/useSymptomSubmit';
import {useNetworkSync, useRiskScore, useRiskScoreHistory} from '@/hooks/useRiskScore';
import {getPatientSession} from '@/lib/patientSession';
import {mmkv} from '@/lib/storage';
import {
  queueSymptomReport, flushSymptomQueue, getPendingReportCount, migrateLegacySymptomQueue,
} from '@/lib/symptomQueue';
import {ApiResponse, AuthTokens, SymptomResponse, UserProfile} from '@/types';

jest.mock('@/lib/storage', () => {
  const values = new Map<string, string>();
  const failures = new Set<string>();
  return {values, failures, mmkv: {
    getString: jest.fn((key: string) => values.get(key)),
    set: jest.fn((key: string, value: string) => {
      if (failures.has(key)) throw new Error('Device storage write failed');
      values.set(key, value);
    }),
    delete: jest.fn((key: string) => { values.delete(key); }),
  }};
});
jest.mock('react-native-mmkv', () => {
  const stores = new Map<string, Map<string, string>>();
  const failures = new Set<string>();
  return {stores, failures, MMKV: jest.fn().mockImplementation(({id}: {id: string}) => {
    if (!stores.has(id)) stores.set(id, new Map());
    const values = stores.get(id)!;
    return {
      getString: jest.fn((key: string) => values.get(key)),
      set: jest.fn((key: string, value: string) => {
        if (failures.has(`${id}:${key}`)) throw new Error('Legacy storage write failed');
        values.set(key, value);
      }),
      delete: jest.fn((key: string) => { values.delete(key); }),
    };
  })};
});
jest.mock('expo-secure-store', () => {
  const values = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (key: string) => values.get(key) || null),
    setItemAsync: jest.fn(async (key: string, value: string) => { values.set(key, value); }),
    deleteItemAsync: jest.fn(async (key: string) => { values.delete(key); }),
  };
});
jest.mock('expo-crypto', () => ({randomUUID: jest.fn()}));
jest.mock('@/services/auth', () => ({authService: {
  login: jest.fn(), logout: jest.fn(), getStoredTokens: jest.fn(),
  getUserProfile: jest.fn(), refreshAccessToken: jest.fn(),
}}));
jest.mock('@/services/api', () => ({apiClient: {get: jest.fn(), post: jest.fn()}}));
jest.mock('@react-native-community/netinfo', () => ({addEventListener: jest.fn()}));

const auth = jest.mocked(authService);
const api = {get: apiClient.get as jest.Mock, post: apiClient.post as jest.Mock};
const values: Map<string, string> = jest.requireMock('@/lib/storage').values;
const failures: Set<string> = jest.requireMock('@/lib/storage').failures;
const legacyStores: Map<string, Map<string, string>> = jest.requireMock('react-native-mmkv').stores;
const legacyFailures: Set<string> = jest.requireMock('react-native-mmkv').failures;
const patientA = 'patient-a';
const patientB = 'patient-b';

function user(id: string): UserProfile {
  return {id, email: `${id}@example.test`, name: id, role: 'patient',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z'};
}
function tokens(id: string): AuthTokens {
  return {access_token: `access-${id}`, refresh_token: `refresh-${id}`,
    expires_in: 3600, token_type: 'Bearer'};
}
function response(id: string): ApiResponse<SymptomResponse> {
  return {status: 201, data: {patient_id: id, risk_score: 0.4,
    risk_tier: 'moderate', report_count: 3}};
}
function legacyRecord(owner: unknown, id: unknown) {
  return {patient_id: owner, id, queued_at: '2026-01-01T00:00:00Z', symptoms: ['fever']};
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return {promise, resolve};
}
function createWrapper(client = new QueryClient({defaultOptions: {
  queries: {retry: false, retryDelay: 0, gcTime: Infinity},
  mutations: {retry: false, gcTime: Infinity},
}})) {
  return ({children}: {children: React.ReactNode}) =>
    <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
async function login(id: string) {
  auth.login.mockResolvedValueOnce(tokens(id));
  auth.getUserProfile.mockResolvedValueOnce(user(id));
  await act(async () => { await useAuthStore.getState().login(); });
}
function pending(id: string) {
  return JSON.parse(mmkv.getString(`offline_queue:${id}`) || '[]') as
    {id: string; patient_id: string; symptoms: string[]}[];
}

beforeEach(async () => {
  jest.clearAllMocks();
  auth.logout.mockResolvedValue(undefined);
  await useAuthStore.getState().logout();
  values.clear();
  failures.clear();
  legacyFailures.clear();
  for (const store of legacyStores.values()) store.clear();
  let nextId = 0;
  jest.mocked(randomUUID).mockReset().mockImplementation(() => `queued-${++nextId}`);
  api.post.mockReset().mockResolvedValue(response(patientA));
  api.get.mockReset().mockResolvedValue({data: [], status: 200});
  jest.mocked(NetInfo.addEventListener).mockImplementation(() => () => {});
});

it('shares concurrent flushes, preserves appends during HTTP, and retains only unacknowledged items on failure', async () => {
  await login(patientA);
  const session = getPatientSession();
  queueSymptomReport({patient_id: patientA, symptoms: ['fever']}, session);
  queueSymptomReport({patient_id: patientA, symptoms: ['cough']}, session);
  const first = deferred<ApiResponse<SymptomResponse>>();
  api.post.mockReset().mockReturnValueOnce(first.promise).mockRejectedValueOnce(new Error('Connection lost'));
  const one = flushSymptomQueue(session);
  const two = flushSymptomQueue(session);
  const results = Promise.all([one.catch(error => error), two.catch(error => error)]);
  expect(api.post).toHaveBeenCalledTimes(1);
  queueSymptomReport({patient_id: patientA, symptoms: ['fatigue']}, session);
  first.resolve(response(patientA));
  const outcomes = await results;
  expect(outcomes.every(error => error instanceof Error && error.message === 'Connection lost')).toBe(true);
  expect(api.post).toHaveBeenCalledTimes(2);
  expect(pending(patientA).map(item => item.symptoms)).toEqual([['cough'], ['fatigue']]);
  expect(getPendingReportCount(session)).toBe(2);
  api.post.mockReset().mockResolvedValue(response(patientA));
  expect(await flushSymptomQueue(session)).toBe(2);
  expect(pending(patientA)).toEqual([]);
});

it('never flushes A with B active and ignores an old A acknowledgement before changing queues or risk', async () => {
  await login(patientA);
  const sessionA = getPatientSession();
  queueSymptomReport({patient_id: patientA, symptoms: ['fever']}, sessionA);
  queueSymptomReport({patient_id: patientA, symptoms: ['cough']}, sessionA);
  const first = deferred<ApiResponse<SymptomResponse>>();
  api.post.mockReturnValueOnce(first.promise);
  const old = flushSymptomQueue(sessionA).catch(error => error);
  await login(patientB);
  const sessionB = getPatientSession();
  expect(getPendingReportCount(sessionA)).toBe(0);
  expect(getPendingReportCount(sessionB)).toBe(0);
  expect(await flushSymptomQueue(sessionB)).toBe(0);
  expect(api.post).toHaveBeenCalledTimes(1);
  first.resolve(response(patientA));
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(pending(patientA)).toHaveLength(2);
  expect(useRiskStore.getState().ownerId).toBe(patientB);
  expect(useRiskStore.getState().riskScore).toBeNull();
  expect(api.post).toHaveBeenCalledTimes(1);
  await login(patientA);
  expect(await flushSymptomQueue(getPatientSession())).toBe(2);
  expect(pending(patientA)).toEqual([]);
});

it('does not apply an old symptom mutation success or expose its result after B signs in', async () => {
  await login(patientA);
  const first = deferred<ApiResponse<SymptomResponse>>();
  api.post.mockReturnValueOnce(first.promise);
  const {result} = renderHook(() => useSymptomSubmit(), {wrapper: createWrapper()});
  let outcome!: Promise<unknown>;
  act(() => {
    outcome = result.current.submitReport({report: {patient_id: patientA, symptoms: ['fever']}})
      .catch(error => error);
  });
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  await login(patientB);
  await act(async () => { first.resolve(response(patientA)); await outcome; });
  expect(await outcome).toMatchObject({name: 'SessionChangedError'});
  expect(result.current.data).toBeUndefined();
  expect(result.current.success).toBe(false);
  expect(useRiskStore.getState().riskScore).toBeNull();
  expect(values.has(`risk_cache:${patientB}:last_response`)).toBe(false);
});

it.each(['destination', 'remaining-legacy'] as const)(
  'blocks HTTP after a %s migration failure and deduplicates all partial writes on retry', async failure => {
    await login(patientA);
    const legacy = new MMKV({id: 'offline-queue'});
    const unowned = {symptoms: ['unassigned'], id: 'unowned'};
    const malformed = legacyRecord(patientA, 42);
    const original = JSON.stringify([
      legacyRecord(patientA, 'a-1'), legacyRecord(patientA, 'a-1'),
      legacyRecord(patientB, 'b-1'), unowned, malformed,
    ]);
    legacy.set('offline_queue', original);
    if (failure === 'destination') failures.add(`offline_queue:${patientB}`);
    else legacyFailures.add('offline-queue:offline_queue');
    await expect(flushSymptomQueue(getPatientSession())).rejects.toThrow('migration failed');
    expect(api.post).not.toHaveBeenCalled();
    expect(legacy.getString('offline_queue')).toBe(original);
    expect(pending(patientA).map(item => item.id)).toEqual(['a-1']);
    failures.clear();
    legacyFailures.clear();
    expect(await flushSymptomQueue(getPatientSession())).toBe(1);
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(pending(patientA)).toEqual([]);
    expect(pending(patientB).map(item => item.id)).toEqual(['b-1']);
    expect(JSON.parse(legacy.getString('offline_queue')!)).toEqual([unowned, malformed]);
    migrateLegacySymptomQueue();
    expect(pending(patientA)).toEqual([]); // No re-enqueue after acknowledgement.
  },
);

it('retains unreadable legacy bytes and refuses to sync them', async () => {
  await login(patientA);
  const legacy = new MMKV({id: 'offline-queue'});
  legacy.set('offline_queue', '{unreadable legacy data');
  expect(() => migrateLegacySymptomQueue()).toThrow('could not be read');
  await expect(flushSymptomQueue(getPatientSession())).rejects.toThrow('could not be read');
  expect(api.post).not.toHaveBeenCalled();
  expect(legacy.getString('offline_queue')).toBe('{unreadable legacy data');
});

it('does not claim an offline save when the device write fails, but reports a real successful offline save', async () => {
  await login(patientA);
  const {result} = renderHook(() => useSymptomSubmit(), {wrapper: createWrapper()});
  api.post.mockRejectedValue(new AxiosError('Network Error'));
  failures.add(`offline_queue:${patientA}`);
  let failure: unknown;
  await act(async () => {
    failure = await result.current.submitReport({report: {patient_id: patientA, symptoms: ['fever']}})
      .catch(error => error);
  });
  expect(failure).toBeInstanceOf(Error);
  expect((failure as Error).message).not.toContain('saved locally');
  expect(pending(patientA)).toEqual([]);
  failures.clear();
  await act(async () => {
    failure = await result.current.submitReport({report: {patient_id: patientA, symptoms: ['fever']}})
      .catch(error => error);
  });
  expect((failure as Error).message).toContain('saved locally');
  expect(result.current.getQueuedReportsCount()).toBe(1);
  await login(patientB);
  expect(result.current.getQueuedReportsCount()).toBe(0);
  await login(patientA);
  expect(result.current.getQueuedReportsCount()).toBe(1);
});

it('keeps an accepted report pending if its local acknowledgement cannot be committed', async () => {
  await login(patientA);
  const session = getPatientSession();
  queueSymptomReport({patient_id: patientA, symptoms: ['fever']}, session);
  api.post.mockImplementationOnce(async () => {
    failures.add(`offline_queue:${patientA}`);
    return response(patientA);
  });
  await expect(flushSymptomQueue(session)).rejects.toThrow('acknowledgement could not be saved');
  expect(pending(patientA)).toHaveLength(1);
  expect(api.post).toHaveBeenCalledTimes(1);
});

it('flushes on network restoration before refreshing current-owner risk and history, without parallel replays across hook mounts', async () => {
  await login(patientA);
  queueSymptomReport({patient_id: patientA, symptoms: ['fever']}, getPatientSession());
  let serverCount = 0;
  const gate = deferred<void>();
  api.post.mockImplementation(async () => {
    await gate.promise;
    ++serverCount;
    return response(patientA);
  });
  api.get.mockImplementation(async (url: string) => ({status: 200, data: url.endsWith('/history')
    ? (serverCount ? [{time: '2026-01-01T00:00:00Z', risk_score: 0.4, risk_tier: 'moderate', symptoms: {reported: ['fever']}}] : [])
    : {patient_id: patientA, risk_score: serverCount ? 0.4 : null,
      risk_tier: serverCount ? 'moderate' : null},
  }));
  let notify!: Parameters<typeof NetInfo.addEventListener>[0];
  jest.mocked(NetInfo.addEventListener).mockImplementation(listener => {
    notify = listener;
    return () => {};
  });
  const client = new QueryClient({defaultOptions: {
    queries: {retry: false, retryDelay: 0, gcTime: Infinity},
  }});
  client.setQueryData(['risk-score', patientB], {risk_score: 0.9});
  const {result} = renderHook(() => {
    useNetworkSync();
    useNetworkSync();
    return {risk: useRiskScore(0), history: useRiskScoreHistory(30)};
  }, {wrapper: createWrapper(client)});
  await waitFor(() => expect(result.current.history.data).toEqual([]));
  act(() => {
    notify({isConnected: false, isInternetReachable: false} as Parameters<typeof notify>[0]);
    notify({isConnected: true, isInternetReachable: true} as Parameters<typeof notify>[0]);
    notify({isConnected: true, isInternetReachable: true} as Parameters<typeof notify>[0]);
  });
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(pending(patientA)).toHaveLength(1);
  await act(async () => { gate.resolve(); await gate.promise; });
  await waitFor(() => {
    expect(result.current.risk.riskScore).toBe(0.4);
    expect(result.current.history.data).toHaveLength(1);
  });
  expect(pending(patientA)).toEqual([]);
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(client.getQueryState(['risk-score', patientB])?.isInvalidated).toBe(false);
});
