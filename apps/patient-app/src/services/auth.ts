import * as AuthSession from 'expo-auth-session';
import * as Crypto from 'expo-crypto';
import * as WebBrowser from 'expo-web-browser';
import * as SecureStore from 'expo-secure-store';
import {
  getPatientSession,
  isPatientSessionCurrent,
  SessionChangedError,
  type PatientSession,
} from '@/lib/patientSession';
import {AuthTokens, PKCECodePair, UserProfile} from '@/types';
import {notificationService} from './notifications';

WebBrowser.maybeCompleteAuthSession();

const KEYCLOAK_URL =
  process.env.EXPO_PUBLIC_KEYCLOAK_URL || 'http://127.0.0.1:8080';
const KEYCLOAK_REALM = process.env.EXPO_PUBLIC_KEYCLOAK_REALM || 'cyberepi';
const KEYCLOAK_CLIENT_ID =
  process.env.EXPO_PUBLIC_KEYCLOAK_CLIENT_ID || 'cyberepi-patient-app';
const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

const discovery = {
  authorizationEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth`,
  tokenEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
  revocationEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/revoke`,
};

export class AuthService {
  private static instance: AuthService;
  private refreshPromise: Promise<AuthTokens | null> | null = null;
  private refreshSession: PatientSession | null = null;
  private refreshVersion = -1;
  private credentialVersion = 0;

  static getInstance(): AuthService {
    if (!AuthService.instance) {
      AuthService.instance = new AuthService();
    }
    return AuthService.instance;
  }

  async generatePKCE(): Promise<PKCECodePair> {
    const codeVerifier = this.generateRandomString(128);
    const codeChallenge = await this.sha256(codeVerifier);
    return {
      codeVerifier,
      codeChallenge,
      codeChallengeMethod: 'S256',
    };
  }

  private generateRandomString(length: number): string {
    const bytes = new Uint8Array(Math.ceil(length / 2));
    Crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0'))
      .join('')
      .slice(0, length);
  }

  private async sha256(input: string): Promise<string> {
    const hash = await Crypto.digestStringAsync(
      Crypto.CryptoDigestAlgorithm.SHA256,
      input,
      {encoding: Crypto.CryptoEncoding.BASE64},
    );
    return this.base64UrlEncode(hash);
  }

  private base64UrlEncode(input: string): string {
    return input.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
  }

  private assertCredentialSession(session: PatientSession, version: number): void {
    if (!isPatientSessionCurrent(session) || version !== this.credentialVersion) {
      throw new SessionChangedError();
    }
  }

  private clearCredentials(): string | null {
    ++this.credentialVersion;
    let refreshToken: string | null = null;
    try {
      refreshToken = SecureStore.getItem('refresh_token');
    } catch {
      // A failed read must not prevent attempts to clear the stored secrets.
    }
    let failed = false;
    for (const key of ['access_token', 'refresh_token', 'token_expires_at', 'pkce_code_verifier']) {
      try {
        // SecureStore has no synchronous delete. Empty values remove the
        // secrets atomically within this JS turn; no delayed delete can erase
        // the next login's credentials.
        SecureStore.setItem(key, '');
      } catch {
        failed = true;
      }
    }
    if (failed) throw new Error('Stored credentials could not be cleared. Please try signing out again.');
    return refreshToken;
  }

  async login(): Promise<AuthTokens> {
    const session = getPatientSession();
    const version = ++this.credentialVersion;
    const pkce = await this.generatePKCE();
    this.assertCredentialSession(session, version);
    SecureStore.setItem('pkce_code_verifier', pkce.codeVerifier);

    const request = new AuthSession.AuthRequest({
      clientId: KEYCLOAK_CLIENT_ID,
      scopes: ['openid', 'profile', 'email'],
      redirectUri: AuthSession.makeRedirectUri({scheme: 'cyberepi-patient'}),
      responseType: AuthSession.ResponseType.Code,
      codeChallengeMethod: pkce.codeChallengeMethod as AuthSession.CodeChallengeMethod,
    });
    // Expo otherwise generates a different pair. The browser request and
    // authorization-code exchange must use this exact verifier/challenge.
    request.codeVerifier = pkce.codeVerifier;
    request.codeChallenge = pkce.codeChallenge;
    const result = await request.promptAsync(discovery);
    this.assertCredentialSession(session, version);
    if (result.type !== 'success') throw new Error('Authentication cancelled or failed');
    const code = result.params.code;
    if (!code) throw new Error('Authorization response missing code');
    return this.exchangeCodeForTokens(code, pkce.codeVerifier, session, version);
  }

  private async exchangeCodeForTokens(
    code: string,
    verifier: string,
    session: PatientSession,
    version: number,
  ): Promise<AuthTokens> {
    this.assertCredentialSession(session, version);
    const response = await fetch(discovery.tokenEndpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: KEYCLOAK_CLIENT_ID,
        code,
        redirect_uri: AuthSession.makeRedirectUri({scheme: 'cyberepi-patient'}),
        code_verifier: verifier,
      }).toString(),
    });
    this.assertCredentialSession(session, version);
    if (!response.ok) throw new Error(`Token exchange failed: HTTP ${response.status}`);
    const tokens: AuthTokens = await response.json();
    this.assertCredentialSession(session, version);
    SecureStore.setItem('access_token', tokens.access_token);
    SecureStore.setItem('refresh_token', tokens.refresh_token);
    SecureStore.setItem('token_expires_at', String(Date.now() + tokens.expires_in * 1000));
    SecureStore.setItem('pkce_code_verifier', '');
    return tokens;
  }

  async logout(): Promise<void> {
    const session = getPatientSession();
    const version = this.credentialVersion;
    // Deregister push token BEFORE clearing credentials to use authenticated
    // API call that prevents stale cleanup from unbinding a new owner.
    try {
      await notificationService.deregisterPushToken();
    } catch {
      // Push token deregistration is best-effort; proceed with credential clearing.
    }
    // Verify session hasn't changed during async deregistration
    if (!isPatientSessionCurrent(session) || version !== this.credentialVersion) {
      // Another login started; do not clear its credentials.
      return;
    }
    const refreshToken = this.clearCredentials();
    // Local credentials are already cleared before any remote I/O. Nothing
    // after this await may mutate credentials belonging to a later login.
    if (refreshToken) {
      try {
        await fetch(discovery.revocationEndpoint, {
          method: 'POST',
          headers: {'Content-Type': 'application/x-form-urlencoded'},
          body: new URLSearchParams({
            client_id: KEYCLOAK_CLIENT_ID,
            token: refreshToken,
            token_type_hint: 'refresh_token',
          }).toString(),
        });
      } catch {
        // Remote revocation is best-effort; local sign-out has completed.
      }
    }
  }

  async getStoredTokens(): Promise<AuthTokens | null> {
    const session = getPatientSession();
    const version = this.credentialVersion;
    const accessToken = SecureStore.getItem('access_token');
    const refreshToken = SecureStore.getItem('refresh_token');
    const expiry = SecureStore.getItem('token_expires_at');
    this.assertCredentialSession(session, version);
    if (!accessToken || !refreshToken || !expiry) return null;
    const expiresAt = Number(expiry);
    if (!Number.isFinite(expiresAt) || expiresAt - Date.now() < 60000) {
      const refreshed = await this.refreshAccessToken();
      if (!isPatientSessionCurrent(session)) throw new SessionChangedError();
      // A denied refresh intentionally clears credentials and returns null.
      if (refreshed) this.assertCredentialSession(session, version);
      return refreshed;
    }
    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_in: Math.floor((expiresAt - Date.now()) / 1000),
      token_type: 'Bearer',
    };
  }

  async refreshAccessToken(): Promise<AuthTokens | null> {
    const session = getPatientSession();
    const version = this.credentialVersion;
    if (this.refreshPromise && this.refreshVersion === version &&
      this.refreshSession && isPatientSessionCurrent(this.refreshSession)) {
      return this.refreshPromise;
    }
    const promise = (async () => {
      const refreshToken = SecureStore.getItem('refresh_token');
      this.assertCredentialSession(session, version);
      if (!refreshToken) {
        this.clearCredentials();
        return null;
      }
      const response = await fetch(discovery.tokenEndpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({
          grant_type: 'refresh_token',
          client_id: KEYCLOAK_CLIENT_ID,
          refresh_token: refreshToken,
        }).toString(),
      });
      this.assertCredentialSession(session, version);
      if (!response.ok) {
        let reason: unknown;
        try {
          const body = await response.json();
          reason = body?.error;
        } catch {
          // Classification still works for a non-JSON 401/403 response.
        }
        this.assertCredentialSession(session, version);
        if (response.status === 401 || response.status === 403 || reason === 'invalid_grant') {
          this.clearCredentials();
          return null;
        }
        throw new Error(`Session refresh is temporarily unavailable (HTTP ${response.status}). Please try again.`);
      }
      const received: AuthTokens = await response.json();
      this.assertCredentialSession(session, version);
      const tokens = {...received, refresh_token: received.refresh_token || refreshToken};
      SecureStore.setItem('access_token', tokens.access_token);
      SecureStore.setItem('refresh_token', tokens.refresh_token);
      SecureStore.setItem('token_expires_at', String(Date.now() + tokens.expires_in * 1000));
      return tokens;
    })().finally(() => {
      if (this.refreshPromise === promise) {
        this.refreshPromise = null;
        this.refreshSession = null;
      }
    });
    this.refreshPromise = promise;
    this.refreshSession = session;
    this.refreshVersion = version;
    return promise;
  }

  async getUserProfile(): Promise<UserProfile | null> {
    const session = getPatientSession();
    const version = this.credentialVersion;
    const tokens = await this.getStoredTokens();
    if (!isPatientSessionCurrent(session)) throw new SessionChangedError();
    if (!tokens) return null;
    this.assertCredentialSession(session, version);
    const response = await fetch(`${API_BASE_URL}/patients/me`, {
      headers: {Authorization: `Bearer ${tokens.access_token}`},
    });
    this.assertCredentialSession(session, version);
    if (!response.ok) {
      if ([401, 403, 404].includes(response.status)) return null;
      throw new Error(`Patient profile is temporarily unavailable (HTTP ${response.status}). Please try again.`);
    }
    const patient = await response.json();
    this.assertCredentialSession(session, version);
    return {
      id: patient.id, // Local patient UUID, deliberately not the Keycloak sub.
      email: patient.email,
      name: `${patient.first_name || ''} ${patient.last_name || ''}`.trim(),
      phone: patient.phone,
      role: 'patient',
      created_at: patient.created_at || new Date().toISOString(),
      updated_at: patient.updated_at || new Date().toISOString(),
    };
  }
}

export const authService = AuthService.getInstance();
