import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { SymptomResponse } from '@/types';
import { apiClient } from '@/services/api';
import { useAuthStore } from '@/store/authStore';
import { useRiskStore } from '@/store/riskStore';
import { MMKV } from 'react-native-mmkv';
import NetInfo from '@react-native-community/netinfo';

// Cache for risk score
const cacheStorage = new MMKV({
  id: 'risk-cache',
  encryptionKey: 'risk-cache-encryption-key',
});

interface RiskScoreResponse {
  risk_score: number | null;
  risk_tier: 'low' | 'moderate' | 'consult' | 'urgent' | null;
  updated_at: string;
  recommendations: string[];
}

export function useRiskScore(refreshInterval: number = 5 * 60 * 1000) { // 5 minutes default
  const queryClient = useQueryClient();
  const { user, isAuthenticated } = useAuthStore();
  const { setRiskScore, setInsufficientData, riskScore, riskTier, lastUpdated } = useRiskStore();

  const query = useQuery({
    queryKey: ['risk-score', user?.id],
    queryFn: async (): Promise<RiskScoreResponse> => {
      if (!user?.id) {
        throw new Error('User not authenticated');
      }

      const response = await apiClient.get<RiskScoreResponse>(`/patients/${user.id}/risk`);
      return response.data;
    },
    enabled: isAuthenticated && !!user?.id,
    refetchInterval: refreshInterval,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    staleTime: 2 * 60 * 1000, // 2 minutes
    retry: (failureCount, error) => {
      // Don't retry on 404 (insufficient data)
      if (error instanceof Error && error.message.includes('404')) {
        return false;
      }
      return failureCount < 3;
    },
  });

  // Update store when query data changes
  useEffect(() => {
    if (query.data) {
      const { risk_score, risk_tier, updated_at, recommendations } = query.data;
      
      if (risk_score !== null && risk_tier) {
        setRiskScore(risk_score, risk_tier, recommendations);
      } else {
        setInsufficientData('Insufficient data: Need at least 3 symptom reports');
      }
      
      // Cache the response
      cacheStorage.set('last_risk_response', JSON.stringify(query.data));
    }
  }, [query.data, setRiskScore, setInsufficientData]);

  // Load cached data on mount
  useEffect(() => {
    const cachedData = cacheStorage.getString('last_risk_response');
    if (cachedData && !query.data) {
      try {
        const parsed: RiskScoreResponse = JSON.parse(cachedData);
        queryClient.setQueryData(['risk-score', user?.id], parsed);
      } catch (error) {
        console.error('Failed to parse cached risk data:', error);
      }
    }
  }, [user?.id, queryClient, query.data]);

  // Function to manually refresh risk score
  const refreshRiskScore = () => {
    query.refetch();
  };

  // Function to get time since last update
  const getTimeSinceLastUpdate = (): string => {
    if (!lastUpdated) return 'Never';
    
    const now = new Date();
    const last = new Date(lastUpdated);
    const diffMs = now.getTime() - last.getTime();
    
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  // Function to check if data is stale
  const isDataStale = (): boolean => {
    if (!lastUpdated) return true;
    
    const now = new Date();
    const last = new Date(lastUpdated);
    const diffMs = now.getTime() - last.getTime();
    
    // Consider stale after 10 minutes
    return diffMs > 10 * 60 * 1000;
  };

  return {
    riskScore,
    riskTier,
    lastUpdated,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refreshRiskScore,
    getTimeSinceLastUpdate,
    isDataStale,
  };
}

// Hook for risk score history (for charts)
export function useRiskScoreHistory(days: number = 7) {
  const { user, isAuthenticated } = useAuthStore();

  return useQuery({
    queryKey: ['risk-score-history', user?.id, days],
    queryFn: async () => {
      if (!user?.id) {
        throw new Error('User not authenticated');
      }

      const response = await apiClient.get(
        `/patients/${user.id}/risk/history?days=${days}`
      );
      return response.data;
    },
    enabled: isAuthenticated && !!user?.id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Hook to listen for network changes and sync
export function useNetworkSync() {
  const queryClient = useQueryClient();
  
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener(state => {
      if (state.isConnected) {
        // When network is restored, refetch all queries
        queryClient.refetchQueries({ queryKey: ['risk-score'] });
        queryClient.refetchQueries({ queryKey: ['medications'] });
        queryClient.refetchQueries({ queryKey: ['symptom-history'] });
      }
    });

    return () => unsubscribe();
  }, [queryClient]);
}
