import * as AuthSession from 'expo-auth-session';
import * as Crypto from 'expo-crypto';
import * as WebBrowser from 'expo-web-browser';
import * as SecureStore from 'expo-secure-store';
import { AuthTokens, PKCECodePair, UserProfile } from '@/types';

WebBrowser.maybeCompleteAuthSession();

const KEYCLOAK_URL = process.env.EXPO_PUBLIC_KEYCLOAK_URL || 'https://auth.cyberepi.health';
const KEYCLOAK_REALM = process.env.EXPO_PUBLIC_KEYCLOAK_REALM || 'cyberepi';
const KEYCLOAK_CLIENT_ID = process.env.EXPO_PUBLIC_KEYCLOAK_CLIENT_ID || 'patient-app';

const discovery = {
  authorizationEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth`,
  tokenEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
  revocationEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/revoke`,
  userInfoEndpoint: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo`,
};

export class AuthService {
  private static instance: AuthService;

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
    const array = new Uint8Array(length);
    Crypto.getRandomValues(array);
    return Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }

  private async sha256(input: string): Promise<string> {
    const hash = await Crypto.digestStringAsync(
      Crypto.CryptoDigestAlgorithm.SHA256,
      input
    );
    return this.base64UrlEncode(hash);
  }

  private base64UrlEncode(input: string): string {
    return input
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
  }

  async login(): Promise<AuthTokens> {
    const pkce = await this.generatePKCE();
    
    // Store code verifier for token exchange
    await SecureStore.setItemAsync('pkce_code_verifier', pkce.codeVerifier);

    const authRequest = new AuthSession.AuthRequest({
      clientId: KEYCLOAK_CLIENT_ID,
      scopes: ['openid', 'profile', 'email'],
      redirectUri: AuthSession.makeRedirectUri({
        scheme: 'cyberepi-patient',
      }),
      responseType: AuthSession.ResponseType.Code,
      codeChallenge: pkce.codeChallenge,
      codeChallengeMethod: pkce.codeChallengeMethod as AuthSession.CodeChallengeMethod,
      extraParams: {
        kc_idp_hint: 'keycloak', // Optional: specify identity provider
      },
    });

    const result = await authRequest.promptAsync(discovery);

    if (result.type === 'success') {
      const { code } = result.params;
      if (!code) {
        throw new Error('Authorization response missing code');
      }
      return await this.exchangeCodeForTokens(code);
    } else {
      throw new Error('Authentication cancelled or failed');
    }
  }

  private async exchangeCodeForTokens(code: string): Promise<AuthTokens> {
    const codeVerifier = await SecureStore.getItemAsync('pkce_code_verifier');
    if (!codeVerifier) {
      throw new Error('PKCE code verifier not found');
    }

    const formData = new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: KEYCLOAK_CLIENT_ID,
      code,
      redirect_uri: AuthSession.makeRedirectUri({
        scheme: 'cyberepi-patient',
      }),
      code_verifier: codeVerifier,
    });

    const response = await fetch(discovery.tokenEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData.toString(),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Token exchange failed: ${error}`);
    }

    const tokens: AuthTokens = await response.json();
    
    // Store tokens securely
    await SecureStore.setItemAsync('access_token', tokens.access_token);
    await SecureStore.setItemAsync('refresh_token', tokens.refresh_token);
    
    const expiresAt = Date.now() + tokens.expires_in * 1000;
    await SecureStore.setItemAsync('token_expires_at', expiresAt.toString());

    // Clean up PKCE verifier
    await SecureStore.deleteItemAsync('pkce_code_verifier');

    return tokens;
  }

  async logout(): Promise<void> {
    const refreshToken = await SecureStore.getItemAsync('refresh_token');
    
    if (refreshToken) {
      try {
        // Revoke token at Keycloak
        const formData = new URLSearchParams({
          client_id: KEYCLOAK_CLIENT_ID,
          refresh_token: refreshToken,
        });

        await fetch(discovery.revocationEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData.toString(),
        });
      } catch (error) {
        console.error('Failed to revoke token:', error);
      }
    }

    // Clear stored tokens
    await SecureStore.deleteItemAsync('access_token');
    await SecureStore.deleteItemAsync('refresh_token');
    await SecureStore.deleteItemAsync('token_expires_at');
    await SecureStore.deleteItemAsync('pkce_code_verifier');
  }

  async getStoredTokens(): Promise<AuthTokens | null> {
    try {
      const accessToken = await SecureStore.getItemAsync('access_token');
      const refreshToken = await SecureStore.getItemAsync('refresh_token');
      const expiresAt = await SecureStore.getItemAsync('token_expires_at');

      if (!accessToken || !refreshToken || !expiresAt) {
        return null;
      }

      // Check if token is expired or will expire within 60 seconds
      const now = Date.now();
      const expiryTime = parseInt(expiresAt, 10);
      
      if (expiryTime - now < 60000) {
        // Token will expire soon, refresh it
        const refreshed = await this.refreshAccessToken();
        return refreshed;
      }

      return {
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_in: Math.floor((expiryTime - now) / 1000),
        token_type: 'Bearer',
      };
    } catch (error) {
      console.error('Failed to retrieve stored tokens:', error);
      return null;
    }
  }

  async refreshAccessToken(): Promise<AuthTokens | null> {
    try {
      const refreshToken = await SecureStore.getItemAsync('refresh_token');
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      const formData = new URLSearchParams({
        grant_type: 'refresh_token',
        client_id: KEYCLOAK_CLIENT_ID,
        refresh_token: refreshToken,
      });

      const response = await fetch(discovery.tokenEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
      });

      if (!response.ok) {
        throw new Error('Token refresh failed');
      }

      const tokens: AuthTokens = await response.json();
      
      // Update stored tokens
      await SecureStore.setItemAsync('access_token', tokens.access_token);
      if (tokens.refresh_token) {
        await SecureStore.setItemAsync('refresh_token', tokens.refresh_token);
      }
      
      const expiresAt = Date.now() + tokens.expires_in * 1000;
      await SecureStore.setItemAsync('token_expires_at', expiresAt.toString());

      return tokens;
    } catch (error) {
      console.error('Token refresh failed:', error);
      await this.logout();
      return null;
    }
  }

  async getUserProfile(): Promise<UserProfile | null> {
    try {
      const tokens = await this.getStoredTokens();
      if (!tokens) {
        return null;
      }

      const response = await fetch(discovery.userInfoEndpoint, {
        headers: {
          Authorization: `Bearer ${tokens.access_token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch user profile');
      }

      const profile = await response.json();
      
      // Transform Keycloak profile to our UserProfile format
      return {
        id: profile.sub,
        email: profile.email,
        name: profile.name || profile.preferred_username,
        phone: profile.phone_number,
        role: profile.realm_access?.roles?.includes('physician') ? 'physician' : 
              profile.realm_access?.roles?.includes('admin') ? 'admin' : 'patient',
        created_at: profile.created_at || new Date().toISOString(),
        updated_at: profile.updated_at || new Date().toISOString(),
      };
    } catch (error) {
      console.error('Failed to fetch user profile:', error);
      return null;
    }
  }
}

export const authService = AuthService.getInstance();
