import {useMutation, useQueryClient} from '@tanstack/react-query';
import {SymptomReport, SymptomResponse} from '@/types';
import {apiClient} from '@/services/api';
import {MMKV} from 'react-native-mmkv';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {Alert, Linking} from 'react-native';
import {randomUUID} from 'expo-crypto';

// Offline queue storage
const offlineStorage = new MMKV({
  id: 'offline-queue',
  encryptionKey: 'offline-encryption-key',
});

const CRISIS_LINE = 'tel:911'; // Local crisis line placeholder

interface SymptomSubmitVariables {
  report: SymptomReport;
}

export function useSymptomSubmit() {
  const queryClient = useQueryClient();
  const {user} = useAuthStore();
  const {setRiskScore, setInsufficientData} = useRiskStore();

  const mutation = useMutation<SymptomResponse, Error, SymptomSubmitVariables>({
    mutationFn: async ({report}) => {
      // Ensure patient_id is set from current user
      if (!user?.id) {
        throw new Error('User not authenticated');
      }

      const reportWithPatient = {
        ...report,
        patient_id: user.id,
      };

      try {
        const response = await apiClient.post<SymptomResponse>(
          '/symptoms',
          reportWithPatient,
        );
        return response.data;
      } catch (error) {
        // If network error, queue for later
        if (error instanceof Error && error.message.includes('Network Error')) {
          await queueReportOffline(reportWithPatient);
          throw new Error(
            'Network unavailable. Report saved locally and will sync when online.',
          );
        }
        throw error;
      }
    },
    onSuccess: data => {
      if (data.risk_score !== null && data.risk_tier) {
        // Update risk store with new score
        setRiskScore(data.risk_score, data.risk_tier);

        // Show urgent alert if needed
        if (data.risk_tier === 'urgent') {
          Alert.alert(
            'Urgent Risk Detected',
            'Your risk score indicates immediate medical attention is needed. Please call the crisis line.',
            [
              {text: 'Cancel', style: 'cancel'},
              {text: 'Call Now', onPress: () => makeEmergencyCall()},
            ],
            {cancelable: false},
          );
        }
      } else {
        // Insufficient data
        setInsufficientData(
          data.message || 'Insufficient data: Need at least 3 symptom reports',
        );
      }

      // Invalidate related queries
      queryClient.invalidateQueries({queryKey: ['risk-score']});
      queryClient.invalidateQueries({queryKey: ['symptom-history']});
    },
    onError: error => {
      console.error('Symptom submission error:', error);
      // Error is handled by the UI component
    },
  });

  // Function to queue reports when offline
  const queueReportOffline = async (report: SymptomReport) => {
    try {
      const existingQueue = offlineStorage.getString('offline_queue');
      const queue = existingQueue ? JSON.parse(existingQueue) : [];

      // Add timestamp and unique ID
      const queuedReport = {
        ...report,
        id: generateId(),
        queued_at: new Date().toISOString(),
      };

      queue.push(queuedReport);
      offlineStorage.set('offline_queue', JSON.stringify(queue));
    } catch (error) {
      console.error('Failed to queue report offline:', error);
    }
  };

  // Function to sync queued reports
  const syncQueuedReports = async () => {
    try {
      const existingQueue = offlineStorage.getString('offline_queue');
      if (!existingQueue) return [];

      const queue = JSON.parse(existingQueue);
      const syncedReports: string[] = [];

      for (const queuedReport of queue) {
        try {
          // Remove queue-specific fields before sending
          const {id, queued_at, ...report} = queuedReport;

          await apiClient.post<SymptomResponse>('/symptoms', report);
          syncedReports.push(queuedReport.id);
        } catch (error) {
          console.error('Failed to sync queued report:', error);
          // Continue with next report
        }
      }

      // Remove synced reports from queue
      const remainingQueue = queue.filter(
        (r: {id: string}) => !syncedReports.includes(r.id),
      );
      offlineStorage.set('offline_queue', JSON.stringify(remainingQueue));

      return syncedReports.length;
    } catch (error) {
      console.error('Failed to sync queued reports:', error);
      return 0;
    }
  };

  // Function to get queued reports count
  const getQueuedReportsCount = (): number => {
    try {
      const existingQueue = offlineStorage.getString('offline_queue');
      if (!existingQueue) return 0;

      const queue = JSON.parse(existingQueue);
      return queue.length;
    } catch (error) {
      console.error('Failed to get queued reports count:', error);
      return 0;
    }
  };

  return {
    submitReport: mutation.mutate,
    isSubmitting: mutation.isPending,
    error: mutation.error,
    success: mutation.isSuccess,
    data: mutation.data,
    syncQueuedReports,
    getQueuedReportsCount,
  };
}

// Helper function to generate a unique ID
function generateId(): string {
  try {
    return randomUUID();
  } catch {
    return Math.random().toString(36).slice(2, 11);
  }
}

// Helper function to make emergency call
function makeEmergencyCall() {
  Linking.openURL(CRISIS_LINE).catch(err => {
    console.error('Failed to open crisis line:', err);
  });
}
