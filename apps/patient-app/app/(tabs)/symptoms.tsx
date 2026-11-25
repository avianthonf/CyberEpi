import React, {useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import {router} from 'expo-router';
import {Ionicons} from '@expo/vector-icons';
import {SymptomForm} from '@/components/SymptomForm';
import {useSymptomSubmit} from '@/hooks/useSymptomSubmit';

export default function SymptomsScreen() {
  const [showForm, setShowForm] = useState(false);
  const {isSubmitting, getQueuedReportsCount} = useSymptomSubmit();

  const handleSymptomSubmit = async () => {
    setShowForm(false);
    Alert.alert(
      'Success',
      'Your symptom report has been submitted successfully.',
      [
        {text: 'OK', onPress: () => router.push('/(tabs)/home')},
        {text: 'Report Another', onPress: () => setShowForm(true)},
      ],
    );
  };

  const handleViewHistory = () => {
    router.push('/(tabs)/history');
  };

  const queuedCount = getQueuedReportsCount();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Symptom Tracking</Text>
        <Text style={styles.subtitle}>
          Track your daily symptoms to monitor your health status
        </Text>
      </View>

      {/* Queued Reports Notice */}
      {queuedCount > 0 && (
        <View style={styles.queuedNotice}>
          <Ionicons name="wifi-outline" size={20} color="#f59e0b" />
          <View style={styles.queuedContent}>
            <Text style={styles.queuedTitle}>
              {queuedCount} report{queuedCount > 1 ? 's' : ''} queued
            </Text>
            <Text style={styles.queuedSubtitle}>
              Reports will sync when you're back online
            </Text>
          </View>
        </View>
      )}

      {/* Main Content */}
      {showForm ? (
        <View style={styles.formContainer}>
          <SymptomForm
            onSubmit={handleSymptomSubmit}
            onCancel={() => setShowForm(false)}
          />
        </View>
      ) : (
        <View style={styles.mainContent}>
          {/* Quick Start Card */}
          <TouchableOpacity
            style={styles.primaryCard}
            onPress={() => setShowForm(true)}
            disabled={isSubmitting}>
            <View style={styles.cardHeader}>
              <Ionicons name="add-circle" size={32} color="#3b82f6" />
              <Text style={styles.cardTitle}>Report New Symptoms</Text>
            </View>
            <Text style={styles.cardDescription}>
              Log your current symptoms including temperature, cough, fatigue,
              and more
            </Text>
            <View style={styles.cardFooter}>
              <Text style={styles.cardAction}>Start Report</Text>
              <Ionicons name="arrow-forward" size={16} color="#3b82f6" />
            </View>
          </TouchableOpacity>

          {/* Info Cards */}
          <View style={styles.infoGrid}>
            <View style={styles.infoCard}>
              <Ionicons name="time-outline" size={24} color="#10b981" />
              <Text style={styles.infoTitle}>Daily Tracking</Text>
              <Text style={styles.infoDescription}>
                Report symptoms daily for accurate risk assessment
              </Text>
            </View>

            <View style={styles.infoCard}>
              <Ionicons
                name="shield-checkmark-outline"
                size={24}
                color="#3b82f6"
              />
              <Text style={styles.infoTitle}>Research Privacy Controls</Text>
              <Text style={styles.infoDescription}>
                Privacy mechanisms are experimental. Use synthetic data only.
              </Text>
            </View>

            <View style={styles.infoCard}>
              <Ionicons name="analytics-outline" size={24} color="#f59e0b" />
              <Text style={styles.infoTitle}>Risk Analysis</Text>
              <Text style={styles.infoDescription}>
                Get personalized risk scores based on your symptoms
              </Text>
            </View>

            <View style={styles.infoCard}>
              <Ionicons name="watch-outline" size={24} color="#8b5cf6" />
              <Text style={styles.infoTitle}>Wearable Sync</Text>
              <Text style={styles.infoDescription}>
                Automatically import data from your health devices
              </Text>
            </View>
          </View>

          {/* History Button */}
          <TouchableOpacity
            style={styles.historyButton}
            onPress={handleViewHistory}>
            <Ionicons name="calendar-outline" size={20} color="#6b7280" />
            <Text style={styles.historyButtonText}>View Symptom History</Text>
            <Ionicons name="chevron-forward" size={16} color="#6b7280" />
          </TouchableOpacity>

          {/* Tips Section */}
          <View style={styles.tipsSection}>
            <Text style={styles.tipsTitle}>Tips for Accurate Reporting</Text>
            <View style={styles.tipItem}>
              <Ionicons name="checkmark" size={16} color="#10b981" />
              <Text style={styles.tipText}>
                Measure temperature when at rest for 5 minutes
              </Text>
            </View>
            <View style={styles.tipItem}>
              <Ionicons name="checkmark" size={16} color="#10b981" />
              <Text style={styles.tipText}>
                Use a pulse oximeter for accurate SpO2 readings
              </Text>
            </View>
            <View style={styles.tipItem}>
              <Ionicons name="checkmark" size={16} color="#10b981" />
              <Text style={styles.tipText}>
                Report symptoms at the same time each day
              </Text>
            </View>
            <View style={styles.tipItem}>
              <Ionicons name="checkmark" size={16} color="#10b981" />
              <Text style={styles.tipText}>
                Be honest about all symptoms, even mild ones
              </Text>
            </View>
          </View>
        </View>
      )}
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
  queuedNotice: {
    flexDirection: 'row',
    backgroundColor: '#fffbeb',
    borderWidth: 1,
    borderColor: '#fbbf24',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
    gap: 12,
  },
  queuedContent: {
    flex: 1,
  },
  queuedTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#92400e',
    marginBottom: 4,
  },
  queuedSubtitle: {
    fontSize: 14,
    color: '#b45309',
  },
  formContainer: {
    flex: 1,
  },
  mainContent: {
    flex: 1,
  },
  primaryCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 24,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
    gap: 12,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1f2937',
  },
  cardDescription: {
    fontSize: 16,
    color: '#4b5563',
    lineHeight: 24,
    marginBottom: 20,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardAction: {
    fontSize: 16,
    fontWeight: '600',
    color: '#3b82f6',
  },
  infoGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 24,
  },
  infoCard: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    width: '48%',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
    marginTop: 8,
    marginBottom: 4,
  },
  infoDescription: {
    fontSize: 12,
    color: '#6b7280',
    lineHeight: 16,
  },
  historyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    padding: 16,
    marginBottom: 24,
  },
  historyButtonText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#6b7280',
    flex: 1,
    marginLeft: 12,
  },
  tipsSection: {
    backgroundColor: '#f0fdf4',
    borderWidth: 1,
    borderColor: '#bbf7d0',
    borderRadius: 12,
    padding: 20,
  },
  tipsTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#166534',
    marginBottom: 16,
  },
  tipItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 8,
  },
  tipText: {
    flex: 1,
    fontSize: 14,
    color: '#166534',
    lineHeight: 20,
  },
});
