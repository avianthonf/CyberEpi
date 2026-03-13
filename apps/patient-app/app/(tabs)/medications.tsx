import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { MedCard } from '@/components/MedCard';
import { MedicationScanner } from '@/components/MedicationScanner';
import { useMedicationStore } from '@/store/medicationStore';
import { calculateOverallAdherence } from '@/store/medicationStore';

export default function MedicationsScreen() {
  const [showScanner, setShowScanner] = useState(false);
  const { medications, activeMedications, isLoading } = useMedicationStore();

  const overallAdherence = calculateOverallAdherence(activeMedications);

  const handleMedicationTaken = (medication: any) => {
    Alert.alert(
      'Medication Recorded',
      `${medication.drug_name} marked as taken.`,
      [{ text: 'OK' }]
    );
  };

  const handleScanSuccess = () => {
    // Refresh medications list
  };

  const getAdherenceColor = (rate: number): string => {
    if (rate >= 90) return '#10b981';
    if (rate >= 70) return '#f59e0b';
    return '#ef4444';
  };

  const getAdherenceLabel = (rate: number): string => {
    if (rate >= 90) return 'Excellent';
    if (rate >= 70) return 'Good';
    return 'Needs Improvement';
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Medications</Text>
        <Text style={styles.subtitle}>
          Manage your medications and track adherence
        </Text>
      </View>

      {/* Adherence Summary */}
      {activeMedications.length > 0 && (
        <View style={styles.adherenceCard}>
          <View style={styles.adherenceHeader}>
            <Text style={styles.adherenceTitle}>Overall Adherence</Text>
            <Text
              style={[
                styles.adherencePercentage,
                { color: getAdherenceColor(overallAdherence) },
              ]}
            >
              {overallAdherence}%
            </Text>
          </View>
          <Text
            style={[
              styles.adherenceLabel,
              { color: getAdherenceColor(overallAdherence) },
            ]}
          >
            {getAdherenceLabel(overallAdherence)}
          </Text>
          <View style={styles.adherenceBar}>
            <View
              style={[
                styles.adherenceFill,
                {
                  width: `${overallAdherence}%`,
                  backgroundColor: getAdherenceColor(overallAdherence),
                },
              ]}
            />
          </View>
        </View>
      )}

      {/* Action Buttons */}
      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.primaryButton}
          onPress={() => setShowScanner(true)}
        >
          <Ionicons name="camera-outline" size={20} color="#ffffff" />
          <Text style={styles.primaryButtonText}>Scan Medication</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.secondaryButton}>
          <Ionicons name="add-outline" size={20} color="#3b82f6" />
          <Text style={styles.secondaryButtonText}>Add Manually</Text>
        </TouchableOpacity>
      </View>

      {/* Medications List */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>
          Active Medications ({activeMedications.length})
        </Text>

        {activeMedications.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="medkit-outline" size={48} color="#9ca3af" />
            <Text style={styles.emptyTitle}>No Active Medications</Text>
            <Text style={styles.emptyDescription}>
              Scan or add your medications to get started
            </Text>
            <TouchableOpacity
              style={styles.emptyButton}
              onPress={() => setShowScanner(true)}
            >
              <Text style={styles.emptyButtonText}>Scan First Medication</Text>
            </TouchableOpacity>
          </View>
        ) : (
          activeMedications.map((medication) => (
            <MedCard
              key={medication.id}
              medication={medication}
              onTaken={handleMedicationTaken}
            />
          ))
        )}
      </View>

      {/* Inactive Medications */}
      {medications.some(m => !m.is_active) && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            Inactive Medications ({medications.filter(m => !m.is_active).length})
          </Text>
          {medications
            .filter(m => !m.is_active)
            .map((medication) => (
              <MedCard
                key={medication.id}
                medication={medication}
                onTaken={handleMedicationTaken}
              />
            ))}
        </View>
      )}

      {/* Scanner Modal */}
      <MedicationScanner
        visible={showScanner}
        onClose={() => setShowScanner(false)}
        onSuccess={handleScanSuccess}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  content: {
    padding: 16,
  },
  header: {
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#6b7280',
    lineHeight: 24,
  },
  adherenceCard: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  adherenceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  adherenceTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
  },
  adherencePercentage: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  adherenceLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 12,
  },
  adherenceBar: {
    height: 8,
    backgroundColor: '#e5e7eb',
    borderRadius: 4,
  },
  adherenceFill: {
    height: '100%',
    borderRadius: 4,
  },
  actions: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 24,
  },
  primaryButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3b82f6',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 8,
  },
  primaryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
  },
  secondaryButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#3b82f6',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
    gap: 8,
  },
  secondaryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#3b82f6',
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 16,
  },
  emptyState: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    marginTop: 16,
    marginBottom: 8,
  },
  emptyDescription: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  emptyButton: {
    backgroundColor: '#3b82f6',
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 20,
  },
  emptyButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#ffffff',
  },
});
