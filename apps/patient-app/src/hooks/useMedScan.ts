import {useState} from 'react';
import {Alert} from 'react-native';
import {MedicationScanResponse} from '@/types';
import {medScannerService} from '@/services/medScanner';
import {useAuthStore} from '@/store/authStore';
import {useMedicationStore} from '@/store/medicationStore';
import {
  PatientSession, getPatientSession, assertPatientSession, isPatientSessionCurrent,
} from '@/lib/patientSession';

interface UseMedScanOptions {
  onSuccess?: (medication: MedicationScanResponse) => void;
  onError?: (error: Error) => void;
  onScanTextEntry?: () => void;
}

export function useMedScan(options: UseMedScanOptions = {}) {
  const {user} = useAuthStore();
  const session = getPatientSession();
  const {addMedication} = useMedicationStore();

  const [isScanning, setIsScanning] = useState(false);
  const [showInteractionModal, setShowInteractionModal] = useState(false);
  const [currentMedication, setCurrentMedication] =
    useState<{data: MedicationScanResponse; session: PatientSession} | null>(null);
  const [requestSession, setRequestSession] = useState(session);
  const [error, setError] = useState<string | null>(null);

  const handleScanSuccess = (medication: MedicationScanResponse, scannedSession: PatientSession) => {
    assertPatientSession(scannedSession);
    if (!scannedSession.patientId) throw new Error('Sign in before saving medications.');
    setCurrentMedication({data: medication, session: scannedSession});

    // Check for severe interactions
    if (medScannerService.hasSevereInteractions(medication)) {
      setShowInteractionModal(true);
    } else {
      // Add medication to store (build a Medication from the scan response)
      const now = new Date().toISOString();
      const medToAdd = {
        id: medication.ndc_code || medication.rxnorm_id || now,
        patient_id: scannedSession.patientId,
        drug_name: medication.drug_name || 'Unknown medication',
        adherence_rate: 100,
        is_active: true,
        created_at: now,
        updated_at: now,
      };
      addMedication(scannedSession.patientId, medToAdd);
      options.onSuccess?.(medication);
    }
  };

  const handleScanError = (err: Error) => {
    setError(err.message);
    options.onError?.(err);
  };

  const scanFromCamera = async () => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    setIsScanning(true);
    setError(null);

    setRequestSession(session);
    try {
      assertPatientSession(session);
      const imageUri = await medScannerService.captureFromCamera();
      assertPatientSession(session);
      if (!imageUri) {
        setIsScanning(false);
        return;
      }

      // OCR (image → text) is not wired up yet; route to the manual entry
      // flow so the user can type the label text, then scan.
      Alert.alert(
        'Enter medication text',
        'Image captured. OCR is not yet available — enter the label text (drug name or NDC) to look it up.',
        [{text: 'OK'}],
      );
      options.onScanTextEntry?.();
    } catch (err) {
      if (isPatientSessionCurrent(session)) {
        handleScanError(err instanceof Error ? err : new Error('Scan failed'));
      }
    } finally {
      if (isPatientSessionCurrent(session)) setIsScanning(false);
    }
  };

  const scanFromGallery = async () => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    setIsScanning(true);
    setError(null);
    setRequestSession(session);

    try {
      assertPatientSession(session);
      const imageUri = await medScannerService.pickFromGallery();
      assertPatientSession(session);
      if (!imageUri) {
        setIsScanning(false);
        return;
      }

      Alert.alert(
        'Enter medication text',
        'Image selected. OCR is not yet available — enter the label text (drug name or NDC) to look it up.',
        [{text: 'OK'}],
      );
      options.onScanTextEntry?.();
    } catch (err) {
      if (isPatientSessionCurrent(session)) {
        handleScanError(err instanceof Error ? err : new Error('Scan failed'));
      }
    } finally {
      if (isPatientSessionCurrent(session)) setIsScanning(false);
    }
  };

  const scanFromText = async (ocrText: string) => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    setIsScanning(true);
    setError(null);

    setRequestSession(session);
    try {
      assertPatientSession(session);
      const medication = await medScannerService.scanMedication(
        ocrText,
        user.id,
        session,
      );
      assertPatientSession(session);
      handleScanSuccess(medication, session);
    } catch (err) {
      if (isPatientSessionCurrent(session)) {
        handleScanError(err instanceof Error ? err : new Error('Scan failed'));
      }
    } finally {
      if (isPatientSessionCurrent(session)) setIsScanning(false);
    }
  };

  const handleInteractionModalAccept = () => {
    if (currentMedication && isPatientSessionCurrent(currentMedication.session) && user?.id) {
      const medication = currentMedication.data;
      const now = new Date().toISOString();
      const medToAdd = {
        id: medication.ndc_code || medication.rxnorm_id || now,
        patient_id: user.id,
        drug_name: medication.drug_name || 'Unknown medication',
        adherence_rate: 100,
        is_active: true,
        created_at: now,
        updated_at: now,
      };
      addMedication(user.id, medToAdd);
      options.onSuccess?.(medication);
    }

    setShowInteractionModal(false);
    setCurrentMedication(null);
  };

  const handleInteractionModalReject = () => {
    Alert.alert(
      'Medication Not Added',
      'Please consult with your physician before taking this medication due to potential interactions.',
      [{text: 'OK'}],
    );

    setShowInteractionModal(false);
    setCurrentMedication(null);
  };

  const clearError = () => {
    setError(null);
  };

  return {
    // State
    isScanning: isPatientSessionCurrent(requestSession) && isScanning,
    error: isPatientSessionCurrent(requestSession) ? error : null,
    showInteractionModal: !!currentMedication &&
      isPatientSessionCurrent(currentMedication.session) && showInteractionModal,
    currentMedication: currentMedication && isPatientSessionCurrent(currentMedication.session)
      ? currentMedication.data : null,

    // Actions
    scanFromCamera,
    scanFromGallery,
    scanFromText,
    clearError,

    // Modal handlers
    handleInteractionModalAccept,
    handleInteractionModalReject,
  };
}
