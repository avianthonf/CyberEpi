import * as ImagePicker from 'expo-image-picker';
import {Alert} from 'react-native';
import {MedicationScanRequest, MedicationScanResponse} from '@/types';
import {apiClient} from '@/services/api';
import {PatientSession, assertPatientSession} from '@/lib/patientSession';

export class MedScannerService {
  private static instance: MedScannerService;

  static getInstance(): MedScannerService {
    if (!MedScannerService.instance) {
      MedScannerService.instance = new MedScannerService();
    }
    return MedScannerService.instance;
  }

  // Request camera permissions
  async requestCameraPermission(): Promise<boolean> {
    try {
      const {status} = await ImagePicker.requestCameraPermissionsAsync();
      return status === 'granted';
    } catch (error) {
      console.error('Camera permission request failed:', error);
      return false;
    }
  }

  // Request gallery permissions
  async requestGalleryPermission(): Promise<boolean> {
    try {
      const {status} = await ImagePicker.requestMediaLibraryPermissionsAsync();
      return status === 'granted';
    } catch (error) {
      console.error('Gallery permission request failed:', error);
      return false;
    }
  }

  // Capture image from camera
  async captureFromCamera(): Promise<string | null> {
    try {
      const hasPermission = await this.requestCameraPermission();
      if (!hasPermission) {
        Alert.alert(
          'Permission Required',
          'Camera permission is required to scan medication labels.',
          [{text: 'OK'}],
        );
        return null;
      }

      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [4, 3],
        quality: 0.8,
      });

      if (!result.canceled && result.assets[0]) {
        return result.assets[0].uri;
      }
      return null;
    } catch (error) {
      console.error('Camera capture failed:', error);
      Alert.alert('Error', 'Failed to capture image. Please try again.');
      return null;
    }
  }

  // Pick image from gallery
  async pickFromGallery(): Promise<string | null> {
    try {
      const hasPermission = await this.requestGalleryPermission();
      if (!hasPermission) {
        Alert.alert(
          'Permission Required',
          'Gallery permission is required to select medication images.',
          [{text: 'OK'}],
        );
        return null;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [4, 3],
        quality: 0.8,
      });

      if (!result.canceled && result.assets[0]) {
        return result.assets[0].uri;
      }
      return null;
    } catch (error) {
      console.error('Image selection failed:', error);
      Alert.alert('Error', 'Failed to select image. Please try again.');
      return null;
    }
  }

  // Extract NDC code from OCR text using regex
  extractNDCCode(text: string): string | null {
    // NDC format: XXXXX-XXXX-XX (5-4-2 digits)
    const ndcPatterns = [
      /\b(\d{5})-(\d{4})-(\d{2})\b/g, // Standard format with dashes
      /\b(\d{5})(\d{4})(\d{2})\b/g, // Without dashes
      /\bNDC[:\s]*(\d{5})-(\d{4})-(\d{2})\b/gi, // With NDC prefix
      /\bNDC[:\s]*(\d{5})(\d{4})(\d{2})\b/gi, // With NDC prefix, no dashes
    ];

    for (const pattern of ndcPatterns) {
      const matches = text.match(pattern);
      if (matches && matches.length > 0) {
        // Extract the first match and format it properly
        const cleanMatch = matches[0].replace(/[^\d-]/g, '');
        const digits = cleanMatch.replace(/-/g, '');

        if (digits.length === 11) {
          // Format as XXXXX-XXXX-XX
          return `${digits.slice(0, 5)}-${digits.slice(5, 9)}-${digits.slice(9, 11)}`;
        }
      }
    }

    return null;
  }
  // Extract drug name from OCR text using regex
  extractDrugName(text: string): string | null {
    const match = text.match(/^([A-Za-z\s]+)\s+\d+mg/i);
    return match && match[1] ? match[1].trim() : null;
  }

  // Scan medication from OCR text and send to API.
  // OCR itself (image → text) requires ML Kit, which is not wired up yet;
  // the text comes from the manual-entry field on the scan screen.
  async scanMedication(
    ocrText: string,
    patientId?: string,
    patientSession?: PatientSession,
  ): Promise<MedicationScanResponse> {
    if (patientSession) {
      assertPatientSession(patientSession);
      if (patientSession.patientId !== patientId) {
        throw new Error('Medication scan patient does not match the signed-in patient.');
      }
    }
    const scanRequest: MedicationScanRequest = {
      ocr_text: ocrText,
      ...(patientId ? {patient_id: patientId} : {}),
    };

    const response = await apiClient.post<MedicationScanResponse>(
      '/medications/scan',
      scanRequest,
      patientSession ? {patientSession} : undefined,
    );
    return response.data;
  }

  // Check for severe interactions
  hasSevereInteractions(medication: MedicationScanResponse): boolean {
    return medication.interactions.some(
      interaction =>
        interaction.severity === 'severe' ||
        interaction.severity === 'contraindicated',
    );
  }

  // Get interaction severity color
  getInteractionSeverityColor(severity: string): string {
    switch (severity) {
      case 'moderate':
        return '#f59e0b'; // amber
      case 'severe':
        return '#f97316'; // orange
      case 'contraindicated':
        return '#dc2626'; // red
      default:
        return '#6b7280'; // gray
    }
  }
}

export const medScannerService = MedScannerService.getInstance();
