import { useState } from 'react';
import { Alert, Modal } from 'react-native';
import { MedicationScanResponse } from '@/types';
import { medScannerService } from '@/services/medScanner';
import { useAuthStore } from '@/store/authStore';
import { useMedicationStore } from '@/store/medicationStore';

interface UseMedScanOptions {
  onSuccess?: (medication: MedicationScanResponse) => void;
  onError?: (error: Error) => void;
  onScanTextEntry?: () => void;
}

export function useMedScan(options: UseMedScanOptions = {}) {
  const { user } = useAuthStore();
  const { addMedication } = useMedicationStore();
  
  const [isScanning, setIsScanning] = useState(false);
  const [showInteractionModal, setShowInteractionModal] = useState(false);
  const [currentMedication, setCurrentMedication] = useState<MedicationScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScanSuccess = (medication: MedicationScanResponse) => {
    setCurrentMedication(medication);

    // Check for severe interactions
    if (medScannerService.hasSevereInteractions(medication)) {
      setShowInteractionModal(true);
    } else {
      // Add medication to store (build a Medication from the scan response)
      const now = new Date().toISOString();
      const medToAdd = {
        id: medication.ndc_code || medication.rxnorm_id || now,
        patient_id: user?.id || '',
        drug_name: medication.drug_name || 'Unknown medication',
        adherence_rate: 100,
        is_active: true,
        created_at: now,
        updated_at: now,
      };
      addMedication(medToAdd);
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

    try {
      const imageUri = await medScannerService.captureFromCamera();
      if (!imageUri) {
        setIsScanning(false);
        return;
      }

      // OCR (image → text) is not wired up yet; route to the manual entry
      // flow so the user can type the label text, then scan.
      Alert.alert(
        'Enter medication text',
        'Image captured. OCR is not yet available — enter the label text (drug name or NDC) to look it up.',
        [{ text: 'OK' }]
      );
      options.onScanTextEntry?.();
    } catch (err) {
      console.error('Camera scan error:', err);
      handleScanError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setIsScanning(false);
    }
  };

  const scanFromGallery = async () => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    setIsScanning(true);
    setError(null);

    try {
      const imageUri = await medScannerService.pickFromGallery();
      if (!imageUri) {
        setIsScanning(false);
        return;
      }

      Alert.alert(
        'Enter medication text',
        'Image selected. OCR is not yet available — enter the label text (drug name or NDC) to look it up.',
        [{ text: 'OK' }]
      );
      options.onScanTextEntry?.();
    } catch (err) {
      console.error('Gallery scan error:', err);
      handleScanError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setIsScanning(false);
    }
  };

  const scanFromText = async (ocrText: string) => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    setIsScanning(true);
    setError(null);

    try {
      const medication = await medScannerService.scanMedication(ocrText, user.id);
      handleScanSuccess(medication);
    } catch (err) {
      console.error('Text scan error:', err);
      handleScanError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setIsScanning(false);
    }
  };

  const handleInteractionModalAccept = () => {
    if (currentMedication && user?.id) {
      const now = new Date().toISOString();
      const medToAdd = {
        id: currentMedication.ndc_code || currentMedication.rxnorm_id || now,
        patient_id: user.id,
        drug_name: currentMedication.drug_name || 'Unknown medication',
        adherence_rate: 100,
        is_active: true,
        created_at: now,
        updated_at: now,
      };
      addMedication(medToAdd);
      options.onSuccess?.(currentMedication);
    }

    setShowInteractionModal(false);
    setCurrentMedication(null);
  };

  const handleInteractionModalReject = () => {
    Alert.alert(
      'Medication Not Added',
      'Please consult with your physician before taking this medication due to potential interactions.',
      [{ text: 'OK' }]
    );
    
    setShowInteractionModal(false);
    setCurrentMedication(null);
  };

  const clearError = () => {
    setError(null);
  };

  return {
    // State
    isScanning,
    error,
    showInteractionModal,
    currentMedication,
    
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
