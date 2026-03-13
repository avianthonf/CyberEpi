export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number; // seconds
  token_type: 'Bearer';
  scope?: string;
}

export interface UserProfile {
  id: string; // UUID v4
  email: string;
  name: string;
  phone?: string;
  date_of_birth?: string; // ISO-8601 date
  role: 'patient' | 'physician' | 'admin';
  created_at: string; // ISO-8601 UTC
  updated_at: string; // ISO-8601 UTC
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: UserProfile | null;
  tokens: AuthTokens | null;
  error: string | null;
}

export interface PKCECodePair {
  codeVerifier: string;
  codeChallenge: string;
  codeChallengeMethod: 'S256';
}
