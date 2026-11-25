import {create} from 'zustand';
import {persist, createJSONStorage} from 'zustand/middleware';
import {AuthState, UserProfile} from '@/types';
import * as SecureStore from 'expo-secure-store';
import {authService} from '@/services/auth';
import {useRiskStore} from './riskStore';
import {useMedicationStore} from './medicationStore';
import {queryClient} from '@/lib/queryClient';
import {
  changePatientSession,
  getPatientSession,
  isPatientSessionCurrent,
} from '@/lib/patientSession';

interface AuthStore extends AuthState {
  sessionGeneration: number;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  setUser: (user: UserProfile) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  checkAuth: () => Promise<void>;
}

const secureStorage = {
  getItem: (name: string) => SecureStore.getItemAsync(name),
  setItem: (name: string, value: string) => SecureStore.setItemAsync(name, value),
  removeItem: (name: string) => SecureStore.deleteItemAsync(name),
};

let operationVersion = 0;
let authCheck: Promise<void> | null = null;
let authCheckVersion = -1;

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => {
      const publishIdentity = (next: Partial<AuthStore> & {
        user: UserProfile | null;
        isAuthenticated: boolean;
      }, startNewSession = false) => {
        const previous = getPatientSession();
        const patientId = next.isAuthenticated ? next.user?.id || null : null;
        const session = previous.patientId !== patientId || startNewSession
          ? changePatientSession(patientId) : previous;
        if (previous !== session || !patientId) {
          // Publish no new auth identity until all visible health state has
          // synchronously selected that owner. Disk records are not deleted.
          useRiskStore.getState().bindPatient(patientId);
          useMedicationStore.getState().bindPatient(patientId);
          if (previous.patientId) {
            for (const key of ['risk-score', 'risk-score-history']) {
              void queryClient.cancelQueries({queryKey: [key, previous.patientId]});
              queryClient.removeQueries({queryKey: [key, previous.patientId]});
            }
          }
        }
        set({...next, sessionGeneration: session.generation});
      };

      return {
        isAuthenticated: false,
        isLoading: true,
        user: null,
        tokens: null,
        error: null,
        sessionGeneration: getPatientSession().generation,

        login: async () => {
          const operation = ++operationVersion;
          // A login can exchange another account's tokens before returning a
          // profile. Stop old-account requests at the start, not after await.
          publishIdentity({
            user: null, tokens: null, isAuthenticated: false,
            isLoading: true, error: null,
          }, true);
          try {
            const tokens = await authService.login();
            if (operation !== operationVersion) return;
            const user = await authService.getUserProfile();
            if (operation !== operationVersion) return;
            if (!user) {
              const message = 'Patient profile unavailable. Please sign in or complete registration.';
              const logout = get().logout();
              set({error: message});
              await logout;
              throw new Error(message);
            }
            publishIdentity({
              user, tokens, isAuthenticated: true, isLoading: false, error: null,
            });
          } catch (error) {
            if (operation === operationVersion) {
              publishIdentity({
                user: null, tokens: null, isAuthenticated: false, isLoading: false,
                error: error instanceof Error ? error.message : 'Login failed',
              });
            }
            throw error;
          }
        },

        logout: async () => {
          ++operationVersion;
          // Clear visibility before waiting for token revocation/network I/O.
          publishIdentity({
            user: null, tokens: null, isAuthenticated: false,
            isLoading: false, error: null,
          }, true);
          const logoutSession = getPatientSession();
          try {
            await authService.logout();
          } catch (error) {
            if (isPatientSessionCurrent(logoutSession)) {
              set({error: error instanceof Error ? error.message :
                'Stored credentials could not be cleared. Please try signing out again.'});
            }
          }
        },

        refreshToken: async () => {
          const session = getPatientSession();
          try {
            const tokens = await authService.refreshAccessToken();
            if (!isPatientSessionCurrent(session)) return;
            if (!tokens) {
              await get().logout();
            } else {
              set({tokens, error: null});
            }
          } catch (error) {
            if (isPatientSessionCurrent(session)) {
              set({
                error: `Session refresh is temporarily unavailable. ${
                  error instanceof Error ? error.message : 'Please try again.'}`,
              });
            }
            throw error;
          }
        },

        setUser: user => {
          ++operationVersion;
          publishIdentity({user, isAuthenticated: get().isAuthenticated}, get().user?.id !== user.id);
        },
        setLoading: isLoading => set({isLoading}),
        setError: error => set({error}),

        checkAuth: () => {
          if (authCheck && authCheckVersion === operationVersion) return authCheck;
          const operation = ++operationVersion;
          authCheckVersion = operation;
          const session = getPatientSession();
          const promise = (async () => {
            try {
              if (!useAuthStore.persist.hasHydrated()) {
                await useAuthStore.persist.rehydrate();
              }
              if (operation !== operationVersion) return;
              set({isLoading: true, error: null});
              const tokens = await authService.getStoredTokens();
              if (operation !== operationVersion || !isPatientSessionCurrent(session)) return;
              if (!tokens) {
                await get().logout();
                return;
              }
              const user = await authService.getUserProfile();
              if (operation !== operationVersion || !isPatientSessionCurrent(session)) return;
              if (!user) {
                await get().logout();
                return;
              }
              publishIdentity({
                user, tokens, isAuthenticated: true, isLoading: false, error: null,
              });
            } catch (error) {
              if (operation !== operationVersion || !isPatientSessionCurrent(session)) return;
              // A transport/server/storage outage is not a credential denial.
              // Retain verified in-memory ownership and all stored credentials.
              set({
                isLoading: false,
                error: `Session verification is temporarily unavailable. ${
                  error instanceof Error ? error.message : 'Please try again.'}`,
              });
            }
          })().finally(() => {
            if (authCheck === promise) authCheck = null;
          });
          authCheck = promise;
          return promise;
        },
      };
    },
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => secureStorage),
      skipHydration: true,
      partialize: state => ({user: state.user}),
      merge: (persisted, current) => ({
        ...current,
        // A stored profile alone is not proof that today's SecureStore tokens
        // belong to it. Only checkAuth can activate its health records.
        user: current.user || (persisted as Partial<AuthState> | undefined)?.user || null,
      }),
    },
  ),
);
