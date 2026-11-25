import {createHash} from 'crypto';
import {waitFor} from '@testing-library/react-native';
import * as SecureStore from 'expo-secure-store';
import * as AuthSession from 'expo-auth-session';
import * as Crypto from 'expo-crypto';
import {AuthService} from '@/services/auth';
import {changePatientSession} from '@/lib/patientSession';
import {AuthTokens} from '@/types';

jest.mock('expo-secure-store', () => {
  const values = new Map<string, string>();
  return {values,
    getItem: jest.fn((key: string) => values.get(key) || null),
    setItem: jest.fn((key: string, value: string) => { values.set(key, value); }),
  };
});
jest.mock('expo-crypto', () => ({
  getRandomValues: jest.fn(), digestStringAsync: jest.fn(),
  CryptoDigestAlgorithm: {SHA256: 'SHA-256'}, CryptoEncoding: {BASE64: 'base64'},
}));
jest.mock('expo-auth-session', () => ({
  AuthRequest: jest.fn(), makeRedirectUri: jest.fn(({scheme}: {scheme: string}) => `${scheme}://callback`),
  ResponseType: {Code: 'code'}, CodeChallengeMethod: {S256: 'S256'},
}));
jest.mock('expo-web-browser', () => ({maybeCompleteAuthSession: jest.fn()}));

const values: Map<string, string> = jest.requireMock('expo-secure-store').values;
const fetchMock = jest.fn();
let service: AuthService;

function tokens(owner = 'a'): AuthTokens {
  return {access_token: `access-${owner}`, refresh_token: `refresh-${owner}`,
    expires_in: 3600, token_type: 'Bearer'};
}
function seed(owner = 'a', expiry = Date.now() + 3600000) {
  const saved = tokens(owner);
  values.set('access_token', saved.access_token);
  values.set('refresh_token', saved.refresh_token);
  values.set('token_expires_at', String(expiry));
  return saved;
}
function http(status: number, body: unknown): Response {
  return {ok: status >= 200 && status < 300, status, statusText: String(status),
    json: async () => body} as Response;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return {promise, resolve};
}

beforeEach(() => {
  jest.clearAllMocks();
  values.clear();
  service = new AuthService();
  changePatientSession(null);
  global.fetch = fetchMock;
  fetchMock.mockReset();
  jest.mocked(SecureStore.getItem).mockImplementation(key => values.get(key) || null);
  jest.mocked(SecureStore.setItem).mockImplementation((key, value) => { values.set(key, value); });
  jest.mocked(Crypto.getRandomValues).mockImplementation(bytes => {
    const buffer = bytes as Uint8Array;
    for (let index = 0; index < buffer.length; ++index) buffer[index] = index;
    return bytes;
  });
  jest.mocked(Crypto.digestStringAsync).mockImplementation(async (_algorithm, input, options) =>
    createHash('sha256').update(input).digest(options?.encoding === 'base64' ? 'base64' : 'hex'));
  jest.mocked(AuthSession.AuthRequest).mockImplementation(() => ({
    codeVerifier: '', codeChallenge: '',
    promptAsync: jest.fn(async () => ({type: 'success', params: {code: 'authorized-code'}})),
  }) as unknown as AuthSession.AuthRequest);
});

it('sends the same RFC7636 verifier/challenge and redirect URI through AuthRequest and token exchange', async () => {
  fetchMock.mockResolvedValue(http(200, tokens()));
  expect(await service.login()).toEqual(tokens());
  const constructed = jest.mocked(AuthSession.AuthRequest).mock.results[0];
  if (!constructed || constructed.type !== 'return') {
    throw new Error('The browser authorization request was not constructed.');
  }
  const request = constructed.value as AuthSession.AuthRequest;
  const verifier = request.codeVerifier;
  if (typeof verifier !== 'string') throw new Error('The authorization request has no PKCE verifier.');
  expect(verifier).toMatch(/^[0-9a-f]{128}$/);
  const expected = createHash('sha256').update(verifier).digest('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  expect(request.codeChallenge).toBe(expected);
  const submitted = new URLSearchParams(fetchMock.mock.calls[0][1].body);
  expect(submitted.get('code_verifier')).toBe(verifier);
  expect(submitted.get('redirect_uri')).toBe('cyberepi-patient://callback');
  expect(submitted.get('grant_type')).toBe('authorization_code');
  expect(values.get('access_token')).toBe(tokens().access_token);
});

it('prevents an older cold login from overwriting a newer login even while both started signed out', async () => {
  const oldDigest = deferred<string>();
  jest.mocked(Crypto.digestStringAsync).mockImplementationOnce(() => oldDigest.promise);
  const old = service.login().catch(error => error);
  fetchMock.mockResolvedValue(http(200, tokens('b')));
  expect(await service.login()).toEqual(tokens('b'));
  oldDigest.resolve('old-challenge');
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(values.get('access_token')).toBe('access-b');
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('does not exchange an authorization code returned after the patient session changed', async () => {
  const prompt = deferred<{type: 'success'; params: {code: string}}>();
  jest.mocked(AuthSession.AuthRequest).mockImplementation(() => ({
    codeVerifier: '', codeChallenge: '', promptAsync: () => prompt.promise,
  }) as unknown as AuthSession.AuthRequest);
  const login = service.login().catch(error => error);
  await waitFor(() => expect(AuthSession.AuthRequest).toHaveBeenCalled());
  changePatientSession('patient-b');
  prompt.resolve({type: 'success', params: {code: 'old-code'}});
  expect(await login).toMatchObject({name: 'SessionChangedError'});
  expect(fetchMock).not.toHaveBeenCalled();
});

it.each(['network', 500, 503, 400] as const)(
  'preserves credentials and throws through nested profile/token refresh on transient %s', async failure => {
    seed('a', Date.now() - 1000);
    const before = new Map(values);
    if (failure === 'network') fetchMock.mockRejectedValue(new TypeError('Network request failed'));
    else fetchMock.mockResolvedValue(http(failure, {error: 'temporarily_unavailable'}));
    await expect(service.getUserProfile()).rejects.toThrow();
    expect(values).toEqual(before);
  },
);

it.each([
  {status: 400, error: 'invalid_grant'}, {status: 401, error: 'unauthorized'},
  {status: 403, error: 'forbidden'},
])('clears credentials and returns permanent denial on refresh $status/$error', async failure => {
  seed('a', Date.now() - 1000);
  fetchMock.mockResolvedValue(http(failure.status, {error: failure.error}));
  expect(await service.getStoredTokens()).toBeNull();
  expect(values.get('access_token')).toBe('');
  expect(values.get('refresh_token')).toBe('');
});

it('supports real nested profile → stored tokens → refresh without invalidating its own read', async () => {
  seed('a', Date.now() - 1000);
  fetchMock.mockResolvedValueOnce(http(200, tokens('rotated'))).mockResolvedValueOnce(http(200, {
    id: 'local-patient-a', first_name: 'Patient', last_name: 'A', email: 'a@example.test',
  }));
  expect(await service.getUserProfile()).toMatchObject({id: 'local-patient-a', name: 'Patient A'});
  expect(values.get('refresh_token')).toBe('refresh-rotated');
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('coalesces concurrent refreshes and preserves the existing refresh token when rotation is omitted', async () => {
  seed();
  const pending = deferred<Response>();
  fetchMock.mockReturnValue(pending.promise);
  const one = service.refreshAccessToken();
  const two = service.refreshAccessToken();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  pending.resolve(http(200, {access_token: 'new-access', expires_in: 3600, token_type: 'Bearer'}));
  const results = await Promise.all([one, two]);
  expect(results.every(result => result?.access_token === 'new-access')).toBe(true);
  expect(values.get('refresh_token')).toBe('refresh-a');
});

it('discards an old refresh response after B takes over, rather than changing B credentials', async () => {
  changePatientSession('patient-a');
  seed();
  const pending = deferred<Response>();
  fetchMock.mockReturnValue(pending.promise);
  const old = service.refreshAccessToken().catch(error => error);
  changePatientSession('patient-b');
  seed('b');
  pending.resolve(http(200, tokens('old-rotated-a')));
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(values.get('access_token')).toBe('access-b');
  expect(values.get('refresh_token')).toBe('refresh-b');
});

it.each([401, 403, 404])('returns permanent profile denial on HTTP %s', async status => {
  seed();
  fetchMock.mockResolvedValue(http(status, {}));
  expect(await service.getUserProfile()).toBeNull();
});

it.each(['network', 503] as const)('throws profile %s failures without clearing valid credentials', async failure => {
  seed();
  const before = new Map(values);
  if (failure === 'network') fetchMock.mockRejectedValue(new TypeError('Network request failed'));
  else fetchMock.mockResolvedValue(http(failure, {}));
  await expect(service.getUserProfile()).rejects.toThrow();
  expect(values).toEqual(before);
});

it('guards profile ownership after asynchronous response decoding as well as after HTTP', async () => {
  changePatientSession('patient-a');
  seed();
  const body = deferred<unknown>();
  const decode = jest.fn(() => body.promise);
  fetchMock.mockResolvedValue({ok: true, status: 200, json: decode});
  const old = service.getUserProfile().catch(error => error);
  await waitFor(() => expect(decode).toHaveBeenCalled());
  changePatientSession('patient-b');
  seed('b');
  body.resolve({id: 'old-local-a', email: 'a@example.test'});
  expect(await old).toMatchObject({name: 'SessionChangedError'});
  expect(values.get('access_token')).toBe('access-b');
});

it('clears credentials before remote logout and never clears B after a delayed revocation finishes', async () => {
  seed();
  const revocation = deferred<Response>();
  fetchMock.mockReturnValue(revocation.promise);
  const signingOut = service.logout();
  expect(values.get('access_token')).toBe('');
  expect(values.get('refresh_token')).toBe('');
  changePatientSession('patient-b');
  seed('b');
  revocation.resolve(http(503, {}));
  await signingOut;
  expect(values.get('access_token')).toBe('access-b');
  expect(values.get('refresh_token')).toBe('refresh-b');
});
