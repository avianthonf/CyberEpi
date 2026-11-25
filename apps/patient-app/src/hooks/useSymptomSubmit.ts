import {useEffect, useState, useSyncExternalStore} from 'react';
import {useMutation, useQueryClient} from '@tanstack/react-query';
import axios from 'axios';
import {Alert, Linking} from 'react-native';
import {SymptomReport, SymptomResponse} from '@/types';
import {apiClient} from '@/services/api';
import {useAuthStore} from '@/store/authStore';
import {
  PatientSession, getPatientSession, assertPatientSession, isPatientSessionCurrent,
} from '@/lib/patientSession';
import {
  applySymptomRisk, flushSymptomQueue, getPendingReportCount, queueSymptomReport,
  subscribeQueueChanges, getQueueRevision, migrateLegacySymptomQueue,
} from '@/lib/symptomQueue';

interface SymptomSubmitVariables {
  report: SymptomReport;
  session: PatientSession;
}

export function useSymptomSubmit() {
  const queryClient = useQueryClient();
  // Subscribe to auth transitions; capture the identity in each submitted
  // mutation rather than reading the latest patient's token after an await.
  useAuthStore(state => state.sessionGeneration);
  const session = getPatientSession();
  const revision = useSyncExternalStore(subscribeQueueChanges, getQueueRevision);
  const [queueError, setQueueError] =
    useState<{session: PatientSession; error: Error} | null>(null);

  useEffect(() => {
    try {
      if (session.patientId) migrateLegacySymptomQueue();
      getPendingReportCount(session);
      setQueueError(null);
    } catch (error) {
      setQueueError({session, error: error instanceof Error ? error :
        new Error('Pending reports could not be loaded.')});
    }
  }, [session, revision]);

  const mutation = useMutation<SymptomResponse, Error, SymptomSubmitVariables>({
    mutationKey: ['symptom-submit', session.patientId, session.generation],
    mutationFn: async ({report, session: submittedSession}) => {
      assertPatientSession(submittedSession);
      if (!submittedSession.patientId || report.patient_id !== submittedSession.patientId) {
        throw new Error('The symptom report must belong to the signed-in patient.');
      }
      try {
        const response = await apiClient.post<SymptomResponse>('/symptoms', report, {
          patientSession: submittedSession,
        });
        assertPatientSession(submittedSession);
        if (response.data.patient_id !== submittedSession.patientId) {
          throw new Error('The report response did not match the signed-in patient.');
        }
        return response.data;
      } catch (error) {
        assertPatientSession(submittedSession);
        const networkUnavailable =
          (axios.isAxiosError(error) && !error.response) ||
          (error instanceof Error && /network error|network request failed/i.test(error.message));
        if (networkUnavailable) {
          // Storage/migration errors propagate unchanged: never claim that a
          // report was saved if the local write did not succeed.
          queueSymptomReport(report, submittedSession);
          throw new Error('Network unavailable. Report saved locally and will sync when online.');
        }
        throw error;
      }
    },
    onSuccess: (data, variables) => {
      if (!isPatientSessionCurrent(variables.session)) return;
      applySymptomRisk(data, variables.session);
      if (data.risk_tier === 'urgent') {
        Alert.alert(
          'Research Risk Score',
          'This research-only score is not clinically validated. If you are experiencing a medical emergency, contact local emergency services.',
          [
            {text: 'Cancel', style: 'cancel'},
            {text: 'Call Now', onPress: () => {
              void Linking.openURL('tel:911').catch(() => {
                Alert.alert('Unable to open phone', 'Please contact local emergency services directly.');
              });
            }},
          ],
          {cancelable: false},
        );
      }
      void queryClient.invalidateQueries({
        queryKey: ['risk-score', variables.session.patientId],
      });
      void queryClient.invalidateQueries({
        queryKey: ['risk-score-history', variables.session.patientId],
      });
    },
  });

  const currentMutation = !!mutation.variables &&
    isPatientSessionCurrent(mutation.variables.session);

  const syncQueuedReports = async () => {
    const synced = await flushSymptomQueue(session);
    assertPatientSession(session);
    if (session.patientId && synced > 0) {
      await Promise.all([
        queryClient.invalidateQueries({queryKey: ['risk-score', session.patientId]}),
        queryClient.invalidateQueries({queryKey: ['risk-score-history', session.patientId]}),
      ]);
    }
    return synced;
  };

  const getQueuedReportsCount = (): number => {
    try {
      return getPendingReportCount(session);
    } catch {
      // The companion error is surfaced by the effect above. A malformed queue
      // is retained, never counted as another patient's pending reports.
      return 0;
    }
  };

  return {
    submitReport: ({report}: {report: SymptomReport}) =>
      mutation.mutateAsync({report, session}),
    isSubmitting: currentMutation && mutation.isPending,
    error: (currentMutation ? mutation.error : null) ||
      (queueError && isPatientSessionCurrent(queueError.session) ? queueError.error : null),
    success: currentMutation && mutation.isSuccess,
    data: currentMutation ? mutation.data : undefined,
    syncQueuedReports,
    getQueuedReportsCount,
  };
}
