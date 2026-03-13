import * as ImagePicker from 'expo-image-picker';
import { Alert } from 'react-native';
import { MedicationScanRequest, MedicationScanResponse } from '@/types';
import { apiClient } from '@/services/api';

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
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      return status === 'granted';
    } catch (error) {
      console.error('Camera permission request failed:', error);
      return false;
    }
  }

  // Request gallery permissions
  async requestGalleryPermission(): Promise<boolean> {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
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
          [{ text: 'OK' }]
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
          [{ text: 'OK' }]
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

  // Extract drug name from OCR text (basic implementation)
  extractDrugName(text: string): string | null {
    // Common drug name patterns
    const drugPatterns = [
      /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?))\b/g,
      /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(tablet|capsule|liquid|solution|injection|spray)\b/gi,
    ];

    for (const pattern of drugPatterns) {
      const matches = text.match(pattern);
      if (matches && matches.length > 0) {
        // Extract the drug name part (before the dosage or form)
        const match = matches[0];
        const drugNameMatch = match.match(/^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/);
        if (drugNameMatch) {
          return drugNameMatch[1];
        }
      }
    }

    return null;
  }

  // Simulate OCR processing (in a real app, this would use ML Kit)
  async performOCR(imageUri: string): Promise<string> {
    // This is a mock implementation
    // In a real app, you would use Google ML Kit Text Recognition
    return new Promise((resolve) => {
      setTimeout(() => {
        // Mock OCR result with NDC code
        const mockOCRTexts = [
          'NDC: 12345-678-90\nLisinopril 10mg\nTablets\nTake one tablet daily',
          'NDC 54321-098-76\nMetformin 500mg\nExtended Release\nTablets',
          'NDC: 98765-432-10\nAtorvastatin Calcium 20mg\nTablets',
          'No NDC code found\nAspirin 81mg\nEnteric Coated',
        ];
        resolve(mockOCRTexts[Math.floor(Math.random() * mockOCRTexts.length)]);
      }, 1500); // Simulate processing time
    });
  }

  // Scan medication and send to API
  async scanMedication(imageUri: string, patientId: string): Promise<MedicationScanResponse | null> {
    try {
      // Perform OCR
      const ocrText = await this.performOCR(imageUri);
      
      // Extract NDC code
      const ndcCode = this.extractNDCCode(ocrText);
      
      // Prepare scan request
      const scanRequest: MedicationScanRequest = {
        patient_id: patientId,
        ...(ndcCode ? { ndc_code: ndcCode } : { raw_text: ocrText }),
      };

      // Send to API
      const response = await apiClient.post<MedicationScanResponse>('/medications/scan', scanRequest);
      return response.data;
    } catch (error) {
      console.error('Medication scan failed:', error);
      throw error;
    }
  }

  // Check for severe interactions
  hasSevereInteractions(medication: MedicationScanResponse): boolean {
    return medication.interactions.some(
      interaction => interaction.severity === 'severe' || interaction.severity === 'contraindicated'
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
