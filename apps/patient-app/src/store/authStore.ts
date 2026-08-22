import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { AuthState, UserProfile, AuthTokens } from '@/types';
import * as SecureStore from 'expo-secure-store';
import { authService } from '@/services/auth';

interface AuthStore extends AuthState {
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  setUser: (user: UserProfile) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  checkAuth: () => Promise<void>;
}

const secureStorage = {
  getItem: async (name: string): Promise<string | null> => {
    return await SecureStore.getItemAsync(name);
  },
  setItem: async (name: string, value: string): Promise<void> => {
    await SecureStore.setItemAsync(name, value);
  },
  removeItem: async (name: string): Promise<void> => {
    await SecureStore.deleteItemAsync(name);
  },
};

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      // Initial state
      isAuthenticated: false,
      isLoading: true,
      user: null,
      tokens: null,
      error: null,

      // Actions
      login: async () => {
        try {
          set({ isLoading: true, error: null });
          
          const tokens = await authService.login();
          const user = await authService.getUserProfile();
          
          if (!user) {
            throw new Error('Failed to fetch user profile');
          }
          
          set({
            isAuthenticated: true,
            isLoading: false,
            user,
            tokens,
            error: null,
          });
        } catch (error) {
          set({
            isAuthenticated: false,
            isLoading: false,
            user: null,
            tokens: null,
            error: error instanceof Error ? error.message : 'Login failed',
          });
          throw error;
        }
      },

      logout: async () => {
        try {
          await authService.logout();
        } catch (error) {
          console.error('Logout error:', error);
        } finally {
          set({
            isAuthenticated: false,
            isLoading: false,
            user: null,
            tokens: null,
            error: null,
          });
        }
      },

      refreshToken: async () => {
        try {
          // Force an OAuth2 refresh_token grant against Keycloak. The previous
          // implementation just re-read from storage, so it never actually
          // rotated an expired access token.
          const tokens = await authService.refreshAccessToken();
          if (tokens) {
            set({ tokens });
          } else {
            await get().logout();
          }
        } catch (error) {
          console.error('Token refresh error:', error);
          await get().logout();
        }
      },

      setUser: (user: UserProfile) => {
        set({ user });
      },

      setLoading: (isLoading: boolean) => {
        set({ isLoading });
      },

      setError: (error: string | null) => {
        set({ error });
      },

      checkAuth: async () => {
        try {
          set({ isLoading: true });
          
          const tokens = await authService.getStoredTokens();
          if (!tokens) {
            set({
              isAuthenticated: false,
              isLoading: false,
              user: null,
              tokens: null,
            });
            return;
          }
          
          const user = await authService.getUserProfile();
          if (!user) {
            // Invalid session
            await authService.logout();
            set({
              isAuthenticated: false,
              isLoading: false,
              user: null,
              tokens: null,
            });
            return;
          }
          
          set({
            isAuthenticated: true,
            isLoading: false,
            user,
            tokens,
          });
        } catch (error) {
          console.error('Auth check error:', error);
          set({
            isAuthenticated: false,
            isLoading: false,
            user: null,
            tokens: null,
            error: null,
          });
        }
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => secureStorage),
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        // Don't persist tokens - they're in SecureStore
      }),
    }
  )
);
