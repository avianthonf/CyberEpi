import {AxiosError, AxiosResponse, AxiosPromise, InternalAxiosRequestConfig, type AxiosAdapter} from 'axios';
import {waitFor} from '@testing-library/react-native';
import * as SecureStore from 'expo-secure-store';
import {apiClient} from '@/services/api';
import {authService} from '@/services/auth';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {changePatientSession, getPatientSession} from '@/lib/patientSession';
import {AuthTokens, UserProfile} from '@/types';

jest.mock('expo-secure-store', () => {
  const values = new Map<string, string>();
  return {values,
    getItem: jest.fn((key: string) => values.get(key) || null),
    setItem: jest.fn((key: string, value: string) => { values.set(key, value); }),
    getItemAsync: jest.fn(async (key: string) => values.get(key) || null),
    setItemAsync: jest.fn(async (key: string, value: string) => { values.set(key, value); }),
    deleteItemAsync: jest.fn(async (key: string) => { values.delete(key); }),
  };
});
jest.mock('@/services/auth', () => ({authService: {
  login: jest.fn(), logout: jest.fn(), getStoredTokens: jest.fn(),
  getUserProfile: jest.fn(), refreshAccessToken: jest.fn(),
}}));

const auth = jest.mocked(authService);
const values: Map<string, string> = jest.requireMock('expo-secure-store').values;
interface ApiClientInternal {
  client: {defaults: {adapter: AxiosAdapter}};
}
// Axios exposes an adapter injection seam; the wrapper intentionally keeps it private.
const internal = apiClient as unknown as ApiClientInternal;
const transport = internal.client;

function tokens(owner: string): AuthTokens {
  return {access_token: `access-${owner}`, refresh_token: `refresh-${owner}`,
    expires_in: 3600, token_type: 'Bearer'};
}
function user(id: string): UserProfile {
  return {id, email: `${id}@example.test`, name: id, role: 'patient',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z'};
}
async function login(id: string) {
  auth.login.mockResolvedValueOnce(tokens(id));
  auth.getUserProfile.mockResolvedValueOnce(user(id));
  await useAuthStore.getState().login();
  values.set('access_token', tokens(id).access_token);
  values.set('refresh_token', tokens(id).refresh_token);
}
function ok(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return {config, data, status: 200, statusText: 'OK', headers: {}};
}
function denied(config: InternalAxiosRequestConfig, status = 401): AxiosError {
  return new AxiosError('Request denied', 'ERR_BAD_REQUEST', config, undefined, {
    config, status, statusText: 'Denied', headers: {}, data: {detail: 'Denied'},
  });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return {promise, resolve};
}

beforeEach(async () => {
  jest.clearAllMocks();
  auth.logout.mockResolvedValue(undefined);
  await useAuthStore.getState().logout();
  values.clear();
  jest.mocked(SecureStore.getItem).mockImplementation(key => values.get(key) || null);
});

it('retries a 401 once with refreshed credentials and preserves the public data/status envelope', async () => {
  await login('patient-a');
  let attempts = 0;
  const headers: unknown[] = [];
  transport.defaults.adapter = async config => {
    headers.push(config.headers.Authorization);
    if (++attempts === 1) throw denied(config);
    return ok(config, {result: 'accepted'});
  };
  auth.refreshAccessToken.mockImplementationOnce(async () => {
    values.set('access_token', 'access-refreshed');
    return tokens('refreshed');
  });
  expect(await apiClient.get('/protected')).toEqual({data: {result: 'accepted'}, status: 200});
  expect(headers).toEqual(['Bearer access-patient-a', 'Bearer access-refreshed']);
  expect(attempts).toBe(2);
});

it('clears the visible authenticated owner after permanent refresh denial', async () => {
  await login('patient-a');
  useRiskStore.getState().setRiskScore('patient-a', 0.5, 'moderate');
  transport.defaults.adapter = async config => { throw denied(config); };
  auth.refreshAccessToken.mockResolvedValueOnce(null);
  await expect(apiClient.get('/protected')).rejects.toThrow();
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
  expect(useAuthStore.getState().user).toBeNull();
  expect(useRiskStore.getState().riskScore).toBeNull();
});

it('preserves the current owner and credentials on a transient refresh outage', async () => {
  await login('patient-a');
  const before = new Map(values);
  transport.defaults.adapter = async config => { throw denied(config); };
  auth.refreshAccessToken.mockRejectedValueOnce(new Error('Refresh server temporarily unavailable'));
  await expect(apiClient.get('/protected')).rejects.toThrow('temporarily unavailable');
  expect(useAuthStore.getState().user?.id).toBe('patient-a');
  expect(useAuthStore.getState().isAuthenticated).toBe(true);
  expect(values).toEqual(before);
});

it('does not refresh a forbidden resource request or retry a repeated 401 indefinitely', async () => {
  await login('patient-a');
  let attempts = 0;
  transport.defaults.adapter = async config => { ++attempts; throw denied(config, 403); };
  await expect(apiClient.get('/forbidden')).rejects.toMatchObject({response: {status: 403}});
  expect(attempts).toBe(1);
  expect(auth.refreshAccessToken).not.toHaveBeenCalled();
  attempts = 0;
  transport.defaults.adapter = async config => { ++attempts; throw denied(config); };
  auth.refreshAccessToken.mockResolvedValueOnce(tokens('patient-a'));
  await expect(apiClient.get('/unauthorized')).rejects.toMatchObject({response: {status: 401}});
  expect(attempts).toBe(2);
});

it('rejects an old patient snapshot before any request is sent', async () => {
  await login('patient-a');
  const old = getPatientSession();
  await login('patient-b');
  const adapter = jest.fn<AxiosPromise, [InternalAxiosRequestConfig]>();
  transport.defaults.adapter = adapter;
  await expect(apiClient.post('/symptoms', {patient_id: 'patient-a'}, {patientSession: old}))
    .rejects.toMatchObject({name: 'SessionChangedError'});
  expect(adapter).not.toHaveBeenCalled();
});

it('does not dispatch A data if the patient changes while credentials are being retrieved', async () => {
  await login('patient-a');
  const snapshot = getPatientSession();
  const adapter = jest.fn<AxiosPromise, [InternalAxiosRequestConfig]>();
  transport.defaults.adapter = adapter;
  jest.mocked(SecureStore.getItem).mockImplementationOnce(() => {
    changePatientSession('patient-b');
    return 'access-patient-b';
  });
  await expect(apiClient.post('/symptoms', {patient_id: 'patient-a'}, {patientSession: snapshot}))
    .rejects.toMatchObject({name: 'SessionChangedError'});
  expect(adapter).not.toHaveBeenCalled();
});

it.each([200, 401])('protects even an unscoped old HTTP %s response from affecting B', async status => {
  await login('patient-a');
  const gate = deferred<void>();
  const entered = jest.fn();
  transport.defaults.adapter = async config => {
    entered();
    await gate.promise;
    if (status === 401) throw denied(config);
    return ok(config, {patient_id: 'patient-a', sensitive: 'old response'});
  };
  const old = apiClient.get('/protected').catch(error => error);
  await waitFor(() => expect(entered).toHaveBeenCalled());
  await login('patient-b');
  gate.resolve();
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(useAuthStore.getState().user?.id).toBe('patient-b');
  expect(useAuthStore.getState().isAuthenticated).toBe(true);
  expect(values.get('access_token')).toBe('access-patient-b');
  expect(auth.refreshAccessToken).not.toHaveBeenCalled();
});

it('never retries an A request after a pending refresh resolves in B session', async () => {
  await login('patient-a');
  const refresh = deferred<AuthTokens | null>();
  auth.refreshAccessToken.mockReturnValueOnce(refresh.promise);
  let attempts = 0;
  transport.defaults.adapter = async config => { ++attempts; throw denied(config); };
  const old = apiClient.get('/protected').catch(error => error);
  await waitFor(() => expect(auth.refreshAccessToken).toHaveBeenCalled());
  await login('patient-b');
  refresh.resolve(tokens('old-refreshed-a'));
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(attempts).toBe(1);
  expect(values.get('access_token')).toBe('access-patient-b');
  expect(useAuthStore.getState().isAuthenticated).toBe(true);
});

it('does not send an unauthenticated request when SecureStore cannot be read', async () => {
  const adapter = jest.fn<AxiosPromise, [InternalAxiosRequestConfig]>();
  transport.defaults.adapter = adapter;
  jest.mocked(SecureStore.getItem).mockImplementationOnce(() => { throw new Error('Keystore offline'); });
  await expect(apiClient.get('/protected')).rejects.toThrow('credentials are temporarily unavailable');
  expect(adapter).not.toHaveBeenCalled();
});

it('handles transport errors without a request config and honors an already-aborted query', async () => {
  transport.defaults.adapter = async () => { throw new Error('Connection refused'); };
  await expect(apiClient.get('/protected')).rejects.toThrow('Connection refused');
  const adapter = jest.fn<AxiosPromise, [InternalAxiosRequestConfig]>();
  transport.defaults.adapter = adapter;
  const controller = new AbortController();
  controller.abort();
  await expect(apiClient.get('/protected', undefined, {signal: controller.signal}))
    .rejects.toMatchObject({code: 'ERR_CANCELED'});
  expect(adapter).not.toHaveBeenCalled();
});
