import React, {useState, useEffect} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
  Linking,
} from 'react-native';
import {Ionicons} from '@expo/vector-icons';
import {router} from 'expo-router';
import {RiskGauge} from '@/components/RiskGauge';
import {AlertBanner} from '@/components/AlertBanner';
import {SymptomForm} from '@/components/SymptomForm';
import {useRiskScore} from '@/hooks/useRiskScore';
import {useAuthStore} from '@/store/authStore';
import {useRiskStore} from '@/store/riskStore';
import {useSymptomSubmit} from '@/hooks/useSymptomSubmit';
import {useNetworkSync} from '@/hooks/useRiskScore';
import NetInfo from '@react-native-community/netinfo';

export default function HomeScreen() {
  const [showSymptomForm, setShowSymptomForm] = useState(false);
  const [isOnline, setIsOnline] = useState(true);

  const {user} = useAuthStore();
  const {riskScore, riskTier, refreshRiskScore, getTimeSinceLastUpdate} =
    useRiskScore();
  const {insufficientDataMessage} = useRiskStore();
  const {isSubmitting} = useSymptomSubmit();

  // Network sync
  useNetworkSync();

  useEffect(() => {
    // Check network status
    const unsubscribe = NetInfo.addEventListener(state => {
      setIsOnline(state.isConnected ?? false);
    });

    return () => unsubscribe();
  }, []);

  const handleSymptomSubmit = async () => {
    setShowSymptomForm(false);
    // Refresh risk score after successful submission
    setTimeout(() => {
      refreshRiskScore();
    }, 1000);
  };

  const handleCallPress = () => {
    // In a real app, this would open the phone dialer
    Linking.openURL('tel:988'); // US crisis line
  };

  const handleRefresh = () => {
    refreshRiskScore();
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={false} onRefresh={handleRefresh} />
      }>
      {/* Offline Badge */}
      {!isOnline && (
        <View style={styles.offlineBanner}>
          <Ionicons name="wifi-outline" size={16} color="#ffffff" />
          <Text style={styles.offlineText}>
            Offline - Data will sync when connected
          </Text>
        </View>
      )}

      {/* Welcome Header */}
      <View style={styles.header}>
        <Text style={styles.greeting}>
          Welcome back, {user?.name?.split(' ')[0] || 'User'}
        </Text>
        <Text style={styles.subtitle}>
          Last updated: {getTimeSinceLastUpdate()}
        </Text>
      </View>

      {/* Risk Gauge Section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Your Risk Score</Text>
        <RiskGauge
          score={riskScore}
          tier={riskTier}
          onCallPress={handleCallPress}
        />
        {insufficientDataMessage && (
          <Text style={styles.insufficientDataText}>
            {insufficientDataMessage}
          </Text>
        )}
      </View>

      {/* Alert Banner */}
      {riskTier && riskTier !== 'low' && (
        <View style={styles.section}>
          <AlertBanner
            tier={riskTier}
            showCallButton={riskTier === 'urgent'}
            onCallPress={handleCallPress}
          />
        </View>
      )}

      {/* Quick Actions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Quick Actions</Text>
        <View style={styles.actionsGrid}>
          <TouchableOpacity
            style={[
              styles.actionCard,
              showSymptomForm && styles.actionCardActive,
            ]}
            onPress={() => setShowSymptomForm(!showSymptomForm)}
            disabled={isSubmitting}>
            <Ionicons name="medical-outline" size={24} color="#3b82f6" />
            <Text style={styles.actionTitle}>Report Symptoms</Text>
            <Text style={styles.actionDescription}>
              Log your daily health status
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionCard}
            onPress={() => router.push('/(tabs)/medications')}>
            <Ionicons name="medkit-outline" size={24} color="#3b82f6" />
            <Text style={styles.actionTitle}>Medications</Text>
            <Text style={styles.actionDescription}>
              Manage your medications
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionCard}
            onPress={() => router.push('/(tabs)/history')}>
            <Ionicons name="time-outline" size={24} color="#3b82f6" />
            <Text style={styles.actionTitle}>History</Text>
            <Text style={styles.actionDescription}>
              View your symptom history
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionCard}
            onPress={() => {
              Alert.alert(
                'Emergency Contacts',
                'Crisis Hotline: 988\n\nPoison Control: 1-800-222-1222\n\nYour Physician: [Contact Info]',
                [{text: 'OK'}],
              );
            }}>
            <Ionicons name="call-outline" size={24} color="#ef4444" />
            <Text style={styles.actionTitle}>Emergency</Text>
            <Text style={styles.actionDescription}>Get help now</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Symptom Form Modal */}
      {showSymptomForm && (
        <View style={styles.formOverlay}>
          <View style={styles.formContainer}>
            <SymptomForm
              onSubmit={handleSymptomSubmit}
              onCancel={() => setShowSymptomForm(false)}
            />
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
  offlineBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ef4444',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
    marginBottom: 16,
    gap: 8,
  },
  offlineText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '500',
  },
  header: {
    marginBottom: 24,
  },
  greeting: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#6b7280',
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
  insufficientDataText: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 16,
    fontStyle: 'italic',
  },
  recommendations: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  recommendationItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 8,
  },
  recommendationText: {
    flex: 1,
    fontSize: 14,
    color: '#374151',
    lineHeight: 20,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  actionCard: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    width: '48%',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  actionCardActive: {
    borderColor: '#3b82f6',
    backgroundColor: '#eff6ff',
  },
  actionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginTop: 8,
    marginBottom: 4,
  },
  actionDescription: {
    fontSize: 12,
    color: '#6b7280',
    lineHeight: 16,
  },
  formOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    zIndex: 1000,
  },
  formContainer: {
    flex: 1,
    backgroundColor: '#ffffff',
    marginTop: 100,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
});
