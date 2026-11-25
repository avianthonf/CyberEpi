import {renderHook, act} from '@testing-library/react-native';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {useMedicationStore} from '@/store/medicationStore';
import {authService} from '@/services/auth';
import {changePatientSession} from '@/lib/patientSession';

// Stateful SecureStore mock with sync methods
jest.mock('expo-secure-store', () => {
  const values: Record<string, string> = {};
  return {values,
    getItemAsync: jest.fn(async (key: string) => values[key] || null),
    setItemAsync: jest.fn(async (key: string, value: string) => { values[key] = value; }),
    deleteItemAsync: jest.fn(async (key: string) => { delete values[key]; }),
    getItem: jest.fn((key: string) => values[key] || null),
    setItem: jest.fn((key: string, value: string) => { values[key] = value; }),
  };
});
const mockSecureStoreData: Record<string, string> = jest.requireMock('expo-secure-store').values;

// Mock authService
jest.mock('@/services/auth', () => ({
  authService: {
    login: jest.fn(),
    logout: jest.fn(),
    getStoredTokens: jest.fn(),
    getUserProfile: jest.fn(),
    refreshAccessToken: jest.fn(),
  },
}));

describe('AuthStore', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    Object.keys(mockSecureStoreData).forEach(key => { delete mockSecureStoreData[key]; });
    
    // Reset stores via actual logout
    const authStore = useAuthStore.getState();
    if (authStore.isAuthenticated) {
      await authStore.logout();
    }
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
      tokens: null,
      isLoading: false,
      error: null,
    });
    useRiskStore.getState().bindPatient(null);
    useMedicationStore.getState().bindPatient(null);
    changePatientSession(null);
  });

  describe('login', () => {
    it('should login successfully and store user data', async () => {
      const mockTokens = {
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        email: 'test@example.com',
        name: 'Test User',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toEqual(mockUser);
      expect(result.current.tokens).toEqual(mockTokens);
      expect(result.current.error).toBeNull();
    });

    it('should handle login failure', async () => {
      const error = new Error('Login failed');
      (authService.login as jest.Mock).mockRejectedValue(error);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        try {
          await result.current.login();
        } catch {
          // Expected error
        }
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
      expect(result.current.error).toBe('Login failed');
    });
  });

  describe('logout', () => {
    it('should sign out and clear the visible auth session', async () => {
      // First login
      const mockTokens = {
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        email: 'test@example.com',
        name: 'Test User',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);

      // Then logout
      await act(async () => {
        await result.current.logout();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
      expect(result.current.error).toBeNull();
    });
  });

  describe('token refresh', () => {
    it('should refresh tokens before expiry', async () => {
      const mockTokens = {
        access_token: 'new-access-token',
        refresh_token: 'new-refresh-token',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      (authService.refreshAccessToken as jest.Mock).mockResolvedValue(
        mockTokens,
      );

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.refreshToken();
      });

      expect(result.current.tokens).toEqual(mockTokens);
    });
  });

  describe('failed token refresh', () => {
    it('should logout when refresh fails', async () => {
      (authService.refreshAccessToken as jest.Mock).mockResolvedValue(null);
      (authService.logout as jest.Mock).mockResolvedValue(undefined);

      const {result} = renderHook(() => useAuthStore());

      // Set initial authenticated state
      await act(async () => {
        useAuthStore.setState({
          isAuthenticated: true,
          user: {
            id: 'test-id',
            email: 'test@example.com',
            name: 'Test User',
            role: 'patient',
            created_at: '2024-01-01T00:00:00.000Z',
            updated_at: '2024-01-01T00:00:00.000Z',
          },
          tokens: {
            access_token: 'expired-access-token',
            refresh_token: 'invalid-refresh-token',
            expires_in: 0,
            token_type: 'Bearer',
          },
        });
      });

      await act(async () => {
        await result.current.refreshToken();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
    });
  });

  describe('checkAuth', () => {
    it('should check authentication status and restore session', async () => {
      const mockTokens = {
        access_token: 'stored-access-token',
        refresh_token: 'stored-refresh-token',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        email: 'test@example.com',
        name: 'Test User',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.getStoredTokens as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.checkAuth();
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toEqual(mockUser);
      expect(result.current.tokens).toEqual(mockTokens);
    });

    it('should clear session if no tokens found', async () => {
      (authService.getStoredTokens as jest.Mock).mockResolvedValue(null);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.checkAuth();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
    });

    it('should clear session if user profile not found', async () => {
      (authService.getStoredTokens as jest.Mock).mockResolvedValue({
        access_token: 'valid-token',
        refresh_token: 'valid-refresh',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      });
      (authService.getUserProfile as jest.Mock).mockResolvedValue(null);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.checkAuth();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
    });
  });

  describe('transient errors preserve session', () => {
    it('should preserve authenticated owner on transient getStoredTokens error', async () => {
      // First establish authenticated session
      const mockTokens = {
        access_token: 'token-a',
        refresh_token: 'refresh-a',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: 'patient-a',
        email: 'a@example.com',
        name: 'Patient A',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.id).toBe('patient-a');

      // Now simulate transient error on checkAuth
      (authService.getStoredTokens as jest.Mock).mockRejectedValueOnce(
        new Error('SecureStore unavailable'),
      );

      await act(async () => {
        await result.current.checkAuth();
      });

      // Should preserve the authenticated owner and show useful error
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.id).toBe('patient-a');
      expect(result.current.tokens).toEqual(mockTokens);
      expect(result.current.error).toContain('temporarily unavailable');
    });

    it('should preserve authenticated owner on transient getUserProfile error', async () => {
      const mockTokens = {
        access_token: 'token-b',
        refresh_token: 'refresh-b',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: 'patient-b',
        email: 'b@example.com',
        name: 'Patient B',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);

      // Transient profile error
      (authService.getStoredTokens as jest.Mock).mockResolvedValueOnce(mockTokens);
      (authService.getUserProfile as jest.Mock).mockRejectedValueOnce(
        new Error('Network timeout'),
      );

      await act(async () => {
        await result.current.checkAuth();
      });

      // Preserved
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.id).toBe('patient-b');
      expect(result.current.error).toContain('temporarily unavailable');
    });

    it('should preserve authenticated owner on transient refresh error', async () => {
      const mockTokens = {
        access_token: 'token-c',
        refresh_token: 'refresh-c',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: 'patient-c',
        email: 'c@example.com',
        name: 'Patient C',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      // Transient refresh error
      (authService.refreshAccessToken as jest.Mock).mockRejectedValueOnce(
        new Error('Server unavailable'),
      );

      await act(async () => {
        try {
          await result.current.refreshToken();
        } catch {
          // Expected
        }
      });

      // Should preserve session with error message
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.id).toBe('patient-c');
      expect(result.current.tokens).toEqual(mockTokens);
      expect(result.current.error).toContain('temporarily unavailable');
    });

    it('should logout on permanent null refresh result', async () => {
      const mockTokens = {
        access_token: 'token-d',
        refresh_token: 'refresh-d',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: 'patient-d',
        email: 'd@example.com',
        name: 'Patient D',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      // Permanent denial (null means credentials invalid)
      (authService.refreshAccessToken as jest.Mock).mockResolvedValueOnce(null);
      (authService.logout as jest.Mock).mockResolvedValue(undefined);

      await act(async () => {
        await result.current.refreshToken();
      });

      // Should clear session
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.tokens).toBeNull();
    });

    it('should clear visibility on checkAuth null tokens (permanent logout)', async () => {
      const mockTokens = {
        access_token: 'token-e',
        refresh_token: 'refresh-e',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const mockUser = {
        id: 'patient-e',
        email: 'e@example.com',
        name: 'Patient E',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(mockTokens);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(mockUser);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.isAuthenticated).toBe(true);

      // Null tokens means permanent logout
      (authService.getStoredTokens as jest.Mock).mockResolvedValueOnce(null);
      (authService.logout as jest.Mock).mockResolvedValue(undefined);

      await act(async () => {
        await result.current.checkAuth();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
    });
  });

  describe('checkAuth identity transitions', () => {
    it('should synchronously clear patient A while adopting patient B', async () => {
      // Login as patient A
      const tokensA = {
        access_token: 'token-a',
        refresh_token: 'refresh-a',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const userA = {
        id: 'patient-a',
        email: 'a@example.com',
        name: 'Patient A',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.login as jest.Mock).mockResolvedValue(tokensA);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(userA);

      const {result} = renderHook(() => useAuthStore());

      await act(async () => {
        await result.current.login();
      });

      expect(result.current.user?.id).toBe('patient-a');
      const sessionGenA = result.current.sessionGeneration;

      // Now checkAuth discovers patient B credentials
      const tokensB = {
        access_token: 'token-b',
        refresh_token: 'refresh-b',
        expires_in: 3600,
        token_type: 'Bearer' as const,
      };

      const userB = {
        id: 'patient-b',
        email: 'b@example.com',
        name: 'Patient B',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      (authService.getStoredTokens as jest.Mock).mockResolvedValue(tokensB);
      (authService.getUserProfile as jest.Mock).mockResolvedValue(userB);

      await act(async () => {
        await result.current.checkAuth();
      });

      // Patient B should be active
      expect(result.current.user?.id).toBe('patient-b');
      expect(result.current.tokens).toEqual(tokensB);
      expect(result.current.sessionGeneration).toBeGreaterThan(sessionGenA);
    });
  });

  describe('setters', () => {
    it('should set user correctly', () => {
      const {result} = renderHook(() => useAuthStore());

      const mockUser = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        email: 'test@example.com',
        name: 'Test User',
        role: 'patient' as const,
        created_at: '2024-03-11T10:00:00.000Z',
        updated_at: '2024-03-11T10:00:00.000Z',
      };

      act(() => {
        result.current.setUser(mockUser);
      });

      expect(result.current.user).toEqual(mockUser);
    });

    it('should set loading state correctly', () => {
      const {result} = renderHook(() => useAuthStore());

      act(() => {
        result.current.setLoading(true);
      });

      expect(result.current.isLoading).toBe(true);

      act(() => {
        result.current.setLoading(false);
      });

      expect(result.current.isLoading).toBe(false);
    });

    it('should set error state correctly', () => {
      const {result} = renderHook(() => useAuthStore());

      act(() => {
        result.current.setError('Test error');
      });

      expect(result.current.error).toBe('Test error');

      act(() => {
        result.current.setError(null);
      });

      expect(result.current.error).toBeNull();
    });
  });
});
