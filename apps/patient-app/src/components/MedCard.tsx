import React, {useState} from 'react';
import {View, Text, StyleSheet, TouchableOpacity, Alert} from 'react-native';
import {Ionicons} from '@expo/vector-icons';
import {Medication, MedicationSchedule} from '@/types';
import {useMedicationStore} from '@/store/medicationStore';
import {
  getNextDoseTime,
  isDoseDueSoon,
  isDoseOverdue,
} from '@/store/medicationStore';

interface MedCardProps {
  medication: Medication;
  onPress?: () => void;
  onTaken?: (medication: Medication) => void;
}

export function MedCard({medication, onPress, onTaken}: MedCardProps) {
  const {updateMedication} = useMedicationStore();
  const [isTaking, setIsTaking] = useState(false);

  const nextDoseTime = getNextDoseTime(medication);
  const isDueSoon = isDoseDueSoon(medication);
  const isOverdue = isDoseOverdue(medication);

  const handleMarkAsTaken = async () => {
    setIsTaking(true);

    try {
      // Update medication
      const now = new Date().toISOString();
      await updateMedication(medication.id, {
        last_taken: now,
        // Calculate next dose based on schedule
        next_dose: calculateNextDose(medication.schedule, now),
        adherence_rate: Math.min(100, medication.adherence_rate + 2), // Simple adherence boost
      });

      onTaken?.(medication);
    } catch (error) {
      console.error('Failed to mark medication as taken:', error);
      Alert.alert('Error', 'Failed to update medication');
    } finally {
      setIsTaking(false);
    }
  };

  const calculateNextDose = (
    schedule: MedicationSchedule | undefined,
    lastTaken: string,
  ): string => {
    // Simple calculation - in a real app, this would be more sophisticated
    const hours = schedule?.frequency.includes('twice') === true ? 12 : 24;
    const nextDose = new Date(lastTaken);
    nextDose.setHours(nextDose.getHours() + hours);
    return nextDose.toISOString();
  };

  const getAdherenceColor = (rate: number): string => {
    if (rate >= 90) return '#10b981'; // green
    if (rate >= 70) return '#f59e0b'; // amber
    return '#ef4444'; // red
  };

  const getStatusIcon = (): keyof typeof Ionicons.glyphMap => {
    if (isOverdue) return 'warning';
    if (isDueSoon) return 'time';
    return 'checkmark-circle';
  };

  const getStatusColor = (): string => {
    if (isOverdue) return '#ef4444';
    if (isDueSoon) return '#f59e0b';
    return '#10b981';
  };

  return (
    <TouchableOpacity
      style={[
        styles.container,
        isDueSoon && styles.dueSoonContainer,
        isOverdue && styles.overdueContainer,
      ]}
      onPress={onPress}
      activeOpacity={0.8}>
      <View style={styles.header}>
        <View style={styles.medicationInfo}>
          <Text style={styles.drugName}>{medication.drug_name}</Text>
          <Text style={styles.strength}>
            {medication.strength} • {medication.dosage_form}
          </Text>
        </View>

        <View style={styles.statusContainer}>
          <Ionicons name={getStatusIcon()} size={20} color={getStatusColor()} />
          <Text style={[styles.statusText, {color: getStatusColor()}]}>
            {isOverdue ? 'Overdue' : isDueSoon ? 'Due Soon' : 'On Schedule'}
          </Text>
        </View>
      </View>

      <View style={styles.schedule}>
        <View style={styles.scheduleItem}>
          <Ionicons name="time-outline" size={16} color="#6b7280" />
          <Text style={styles.scheduleText}>
            {medication.schedule?.frequency ?? 'As directed'}
          </Text>
        </View>

        {nextDoseTime && (
          <View style={styles.scheduleItem}>
            <Ionicons name="alarm-outline" size={16} color="#6b7280" />
            <Text style={styles.scheduleText}>Next: {nextDoseTime}</Text>
          </View>
        )}
      </View>

      <View style={styles.footer}>
        <View style={styles.adherenceContainer}>
          <Text style={styles.adherenceLabel}>Adherence</Text>
          <View style={styles.adherenceBar}>
            <View
              style={[
                styles.adherenceFill,
                {
                  width: `${medication.adherence_rate}%`,
                  backgroundColor: getAdherenceColor(medication.adherence_rate),
                },
              ]}
            />
          </View>
          <Text
            style={[
              styles.adherenceValue,
              {color: getAdherenceColor(medication.adherence_rate)},
            ]}>
            {medication.adherence_rate}%
          </Text>
        </View>

        {(isDueSoon || isOverdue) && (
          <TouchableOpacity
            style={[styles.takeButton, isTaking && styles.takeButtonDisabled]}
            onPress={handleMarkAsTaken}
            disabled={isTaking}>
            {isTaking ? (
              <Text style={styles.takeButtonText}>Marking...</Text>
            ) : (
              <>
                <Ionicons name="checkmark" size={16} color="#ffffff" />
                <Text style={styles.takeButtonText}>Taken</Text>
              </>
            )}
          </TouchableOpacity>
        )}
      </View>

      {/* Reminders Badge */}
      {medication.schedule?.reminders.enabled && (
        <View style={styles.reminderBadge}>
          <Ionicons name="notifications-outline" size={12} color="#3b82f6" />
          <Text style={styles.reminderText}>
            {medication.schedule.reminders.times.length} reminder
            {medication.schedule.reminders.times.length > 1 ? 's' : ''}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  dueSoonContainer: {
    borderColor: '#f59e0b',
    backgroundColor: '#fffbeb',
  },
  overdueContainer: {
    borderColor: '#ef4444',
    backgroundColor: '#fef2f2',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  medicationInfo: {
    flex: 1,
  },
  drugName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  strength: {
    fontSize: 14,
    color: '#6b7280',
  },
  statusContainer: {
    alignItems: 'center',
  },
  statusText: {
    fontSize: 12,
    fontWeight: '500',
    marginTop: 4,
  },
  schedule: {
    marginBottom: 16,
  },
  scheduleItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  scheduleText: {
    fontSize: 14,
    color: '#4b5563',
    marginLeft: 8,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  adherenceContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  adherenceLabel: {
    fontSize: 12,
    color: '#6b7280',
    marginRight: 8,
  },
  adherenceBar: {
    flex: 1,
    height: 6,
    backgroundColor: '#e5e7eb',
    borderRadius: 3,
    marginRight: 8,
  },
  adherenceFill: {
    height: '100%',
    borderRadius: 3,
  },
  adherenceValue: {
    fontSize: 12,
    fontWeight: '600',
    minWidth: 32,
    textAlign: 'right',
  },
  takeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#10b981',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    gap: 4,
  },
  takeButtonDisabled: {
    backgroundColor: '#9ca3af',
  },
  takeButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#ffffff',
  },
  reminderBadge: {
    position: 'absolute',
    top: 12,
    right: 12,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 4,
  },
  reminderText: {
    fontSize: 10,
    color: '#3b82f6',
    fontWeight: '500',
  },
});
