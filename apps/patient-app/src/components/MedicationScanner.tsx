import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  ScrollView,
} from 'react-native';
import {Ionicons} from '@expo/vector-icons';
import {useMedScan} from '@/hooks/useMedScan';

interface MedicationScannerProps {
  visible: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function MedicationScanner({
  visible,
  onClose,
  onSuccess,
}: MedicationScannerProps) {
  const {
    isScanning,
    error,
    showInteractionModal,
    currentMedication,
    scanFromCamera,
    scanFromGallery,
    clearError,
    handleInteractionModalAccept,
    handleInteractionModalReject,
  } = useMedScan({
    onSuccess: () => {
      onClose();
      onSuccess?.();
    },
  });

  const handleCameraPress = () => {
    scanFromCamera();
  };

  const handleGalleryPress = () => {
    scanFromGallery();
  };

  const handleClose = () => {
    if (!isScanning) {
      clearError();
      onClose();
    }
  };

  return (
    <>
      <Modal
        visible={visible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={handleClose}>
        <View style={styles.container}>
          {/* Header */}
          <View style={styles.header}>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={handleClose}
              disabled={isScanning}>
              <Ionicons name="close" size={24} color="#374151" />
            </TouchableOpacity>
            <Text style={styles.title}>Scan Medication</Text>
            <View style={styles.placeholder} />
          </View>

          {/* Content */}
          <ScrollView
            style={styles.content}
            showsVerticalScrollIndicator={false}>
            <Text style={styles.description}>
              Scan your medication label using your camera or select an image
              from your gallery. The app will automatically detect the
              medication information.
            </Text>

            {/* Error Message */}
            {error && (
              <View style={styles.errorContainer}>
                <Text style={styles.errorText}>{error}</Text>
                <TouchableOpacity onPress={clearError}>
                  <Text style={styles.errorDismiss}>Dismiss</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Scan Options */}
            <View style={styles.optionsContainer}>
              <TouchableOpacity
                style={[
                  styles.optionButton,
                  isScanning && styles.disabledButton,
                ]}
                onPress={handleCameraPress}
                disabled={isScanning}>
                <View style={styles.optionIcon}>
                  <Ionicons name="camera" size={32} color="#3b82f6" />
                </View>
                <Text style={styles.optionTitle}>Use Camera</Text>
                <Text style={styles.optionDescription}>
                  Take a photo of your medication label
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.optionButton,
                  isScanning && styles.disabledButton,
                ]}
                onPress={handleGalleryPress}
                disabled={isScanning}>
                <View style={styles.optionIcon}>
                  <Ionicons name="images" size={32} color="#3b82f6" />
                </View>
                <Text style={styles.optionTitle}>Choose from Gallery</Text>
                <Text style={styles.optionDescription}>
                  Select an existing photo of your medication
                </Text>
              </TouchableOpacity>
            </View>

            {/* Loading State */}
            {isScanning && (
              <View style={styles.loadingContainer}>
                <Text style={styles.loadingText}>Scanning medication...</Text>
                <Text style={styles.loadingSubtext}>
                  This may take a few seconds
                </Text>
              </View>
            )}

            {/* Tips */}
            <View style={styles.tipsContainer}>
              <Text style={styles.tipsTitle}>Tips for best results:</Text>
              <Text style={styles.tip}>• Ensure good lighting</Text>
              <Text style={styles.tip}>• Hold camera steady</Text>
              <Text style={styles.tip}>• Make sure NDC code is visible</Text>
              <Text style={styles.tip}>• Avoid glare on the label</Text>
            </View>
          </ScrollView>
        </View>
      </Modal>

      {/* Interaction Modal */}
      <Modal
        visible={showInteractionModal}
        animationType="fade"
        transparent={true}
        onRequestClose={handleInteractionModalReject}>
        <View style={styles.modalOverlay}>
          <View style={styles.interactionModal}>
            <View style={styles.interactionHeader}>
              <Ionicons name="warning" size={32} color="#dc2626" />
              <Text style={styles.interactionTitle}>
                Drug Interactions Detected
              </Text>
            </View>

            <ScrollView style={styles.interactionContent}>
              <Text style={styles.interactionDescription}>
                The following interactions were detected for{' '}
                {currentMedication?.drug_name}:
              </Text>

              {currentMedication?.interactions.map((interaction, index) => (
                <View key={index} style={styles.interactionItem}>
                  <Text style={styles.interactingDrug}>
                    {interaction.drug_b_name ?? interaction.drug_b}
                  </Text>
                  <Text
                    style={[
                      styles.interactionSeverity,
                      {
                        color: getInteractionSeverityColor(
                          interaction.severity,
                        ),
                      },
                    ]}>
                    {interaction.severity.toUpperCase()}
                  </Text>
                  <Text style={styles.interactionDescriptionText}>
                    {interaction.description}
                  </Text>
                </View>
              ))}

              <View style={styles.disclaimer}>
                <Text style={styles.disclaimerText}>
                  Please consult with your physician before taking this
                  medication.
                </Text>
              </View>
            </ScrollView>

            <View style={styles.interactionActions}>
              <TouchableOpacity
                style={styles.rejectButton}
                onPress={handleInteractionModalReject}>
                <Text style={styles.rejectButtonText}>Do Not Add</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.acceptButton}
                onPress={handleInteractionModalAccept}>
                <Text style={styles.acceptButtonText}>Add Anyway</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

function getInteractionSeverityColor(severity: string): string {
  switch (severity) {
    case 'moderate':
      return '#f59e0b';
    case 'severe':
      return '#f97316';
    case 'contraindicated':
      return '#dc2626';
    default:
      return '#6b7280';
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  closeButton: {
    padding: 4,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
  },
  placeholder: {
    width: 32,
  },
  content: {
    flex: 1,
    padding: 24,
  },
  description: {
    fontSize: 16,
    color: '#4b5563',
    lineHeight: 24,
    marginBottom: 24,
  },
  errorContainer: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: 8,
    padding: 12,
    marginBottom: 24,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  errorText: {
    flex: 1,
    fontSize: 14,
    color: '#dc2626',
  },
  errorDismiss: {
    fontSize: 14,
    color: '#3b82f6',
    fontWeight: '500',
  },
  optionsContainer: {
    gap: 16,
    marginBottom: 32,
  },
  optionButton: {
    backgroundColor: '#f9fafb',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
  },
  disabledButton: {
    opacity: 0.5,
  },
  optionIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#eff6ff',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 16,
  },
  optionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  optionDescription: {
    fontSize: 14,
    color: '#6b7280',
    flex: 1,
  },
  loadingContainer: {
    alignItems: 'center',
    paddingVertical: 32,
  },
  loadingText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#3b82f6',
    marginBottom: 8,
  },
  loadingSubtext: {
    fontSize: 14,
    color: '#6b7280',
  },
  tipsContainer: {
    backgroundColor: '#f0fdf4',
    borderWidth: 1,
    borderColor: '#bbf7d0',
    borderRadius: 8,
    padding: 16,
  },
  tipsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#166534',
    marginBottom: 8,
  },
  tip: {
    fontSize: 14,
    color: '#166534',
    marginBottom: 4,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  interactionModal: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    maxWidth: 400,
    width: '100%',
    maxHeight: '80%',
  },
  interactionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  interactionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    marginLeft: 12,
  },
  interactionContent: {
    padding: 20,
    maxHeight: 400,
  },
  interactionDescription: {
    fontSize: 14,
    color: '#4b5563',
    marginBottom: 16,
  },
  interactionItem: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  interactingDrug: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  interactionSeverity: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 8,
  },
  interactionDescriptionText: {
    fontSize: 14,
    color: '#4b5563',
    marginBottom: 8,
  },
  interactionRecommendation: {
    fontSize: 14,
    color: '#1f2937',
    fontWeight: '500',
  },
  disclaimer: {
    marginTop: 16,
    padding: 12,
    backgroundColor: '#fef3c7',
    borderRadius: 8,
  },
  disclaimerText: {
    fontSize: 12,
    color: '#92400e',
  },
  interactionActions: {
    flexDirection: 'row',
    padding: 20,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    gap: 12,
  },
  rejectButton: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    alignItems: 'center',
  },
  rejectButtonText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#6b7280',
  },
  acceptButton: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 24,
    backgroundColor: '#dc2626',
    borderRadius: 8,
    alignItems: 'center',
  },
  acceptButtonText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#ffffff',
  },
});
