import { useState } from 'react';
import { Alert, Modal } from 'react-native';
import { MedicationScanResponse } from '@/types';
import { medScannerService } from '@/services/medScanner';
import { useAuthStore } from '@/store/authStore';
import { useMedicationStore } from '@/store/medicationStore';

interface UseMedScanOptions {
  onSuccess?: (medication: MedicationScanResponse) => void;
  onError?: (error: Error) => void;
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
      // Add medication to store
      const medToAdd = {
        ...medication,
        patient_id: user?.id || '',
        adherence_rate: 100,
        is_active: true,
        last_taken: null,
        next_dose: null,
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

      const medication = await medScannerService.scanMedication(imageUri, user.id);
      handleScanSuccess(medication);
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

      const medication = await medScannerService.scanMedication(imageUri, user.id);
      handleScanSuccess(medication);
    } catch (err) {
      console.error('Gallery scan error:', err);
      handleScanError(err instanceof Error ? err : new Error('Scan failed'));
    } finally {
      setIsScanning(false);
    }
  };

  const handleInteractionModalAccept = () => {
    if (currentMedication && user?.id) {
      const medToAdd = {
        ...currentMedication,
        patient_id: user.id,
        adherence_rate: 100,
        is_active: true,
        last_taken: null,
        next_dose: null,
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
    clearError,
    
    // Modal handlers
    handleInteractionModalAccept,
    handleInteractionModalReject,
  };
}
