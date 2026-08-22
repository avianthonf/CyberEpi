import {renderHook, act} from '@testing-library/react-native';
import {useAuthStore} from '@/store/authStore';
import {authService} from '@/services/auth';

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

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
  beforeEach(() => {
    jest.clearAllMocks();
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
    it('should logout and clear all data', async () => {
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
