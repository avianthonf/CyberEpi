import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useWearable } from '@/hooks/useWearable';

interface WearableSyncProps {
  onSyncComplete?: () => void;
}

export function WearableSync({ onSyncComplete }: WearableSyncProps) {
  const {
    wearableData,
    isLoading,
    error,
    isAuthorized,
    requestPermissions,
    refreshData,
  } = useWearable();

  useEffect(() => {
    if (wearableData) {
      onSyncComplete?.();
    }
  }, [wearableData, onSyncComplete]);

  const handleConnect = async () => {
    try {
      await requestPermissions();
    } catch (err) {
      Alert.alert('Error', 'Failed to connect to health services');
    }
  };

  const handleRefresh = () => {
    refreshData();
  };

  const getLastSyncTime = (): string => {
    if (!wearableData?.last_updated) return 'Never';
    
    const now = new Date();
    const lastSync = new Date(wearableData.last_updated);
    const diffMs = now.getTime() - lastSync.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.iconContainer}>
          <Ionicons 
            name="watch-outline" 
            size={24} 
            color={isAuthorized ? '#10b981' : '#9ca3af'} 
          />
        </View>
        <View style={styles.headerContent}>
          <Text style={styles.title}>Health Devices</Text>
          <Text style={styles.subtitle}>
            {isAuthorized ? 'Connected' : 'Not connected'}
          </Text>
        </View>
        <TouchableOpacity onPress={handleRefresh} disabled={isLoading}>
          <Ionicons 
            name="refresh-outline" 
            size={24} 
            color={isLoading ? '#9ca3af' : '#3b82f6'} 
          />
        </TouchableOpacity>
      </View>

      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {!isAuthorized ? (
        <View style={styles.connectContainer}>
          <Text style={styles.connectDescription}>
            Connect your health devices to automatically import vital signs
          </Text>
          <TouchableOpacity
            style={styles.connectButton}
            onPress={handleConnect}
          >
            <Ionicons name="link-outline" size={20} color="#ffffff" />
            <Text style={styles.connectButtonText}>Connect Devices</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.dataContainer}>
          <View style={styles.syncInfo}>
            <Text style={styles.syncLabel}>Last sync:</Text>
            <Text style={styles.syncTime}>{getLastSyncTime()}</Text>
          </View>

          {wearableData && (
            <View style={styles.metricsGrid}>
              {wearableData.heart_rate_bpm && (
                <View style={styles.metricItem}>
                  <Ionicons name="heart-outline" size={16} color="#ef4444" />
                  <Text style={styles.metricLabel}>Heart Rate</Text>
                  <Text style={styles.metricValue}>{wearableData.heart_rate_bpm} bpm</Text>
                </View>
              )}

              {wearableData.spo2_pct && (
                <View style={styles.metricItem}>
                  <Ionicons name="water-outline" size={16} color="#3b82f6" />
                  <Text style={styles.metricLabel}>SpO2</Text>
                  <Text style={styles.metricValue}>{wearableData.spo2_pct}%</Text>
                </View>
              )}

              {wearableData.hrv_rmssd_ms && (
                <View style={styles.metricItem}>
                  <Ionicons name="pulse-outline" size={16} color="#8b5cf6" />
                  <Text style={styles.metricLabel}>HRV</Text>
                  <Text style={styles.metricValue}>{wearableData.hrv_rmssd_ms} ms</Text>
                </View>
              )}

              {wearableData.resting_hr_bpm && (
                <View style={styles.metricItem}>
                  <Ionicons name="bed-outline" size={16} color="#10b981" />
                  <Text style={styles.metricLabel}>Resting HR</Text>
                  <Text style={styles.metricValue}>{wearableData.resting_hr_bpm} bpm</Text>
                </View>
              )}

              {wearableData.sleep_hours && (
                <View style={styles.metricItem}>
                  <Ionicons name="moon-outline" size={16} color="#6366f1" />
                  <Text style={styles.metricLabel}>Sleep</Text>
                  <Text style={styles.metricValue}>{wearableData.sleep_hours} hrs</Text>
                </View>
              )}

              {wearableData.step_count && (
                <View style={styles.metricItem}>
                  <Ionicons name="walk-outline" size={16} color="#f59e0b" />
                  <Text style={styles.metricLabel}>Steps</Text>
                  <Text style={styles.metricValue}>{wearableData.step_count.toLocaleString()}</Text>
                </View>
              )}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f3f4f6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  headerContent: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  subtitle: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 2,
  },
  errorContainer: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    fontSize: 12,
    color: '#dc2626',
  },
  connectContainer: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  connectDescription: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    marginBottom: 16,
    lineHeight: 20,
  },
  connectButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3b82f6',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    gap: 8,
  },
  connectButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#ffffff',
  },
  dataContainer: {
    paddingTop: 8,
  },
  syncInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    paddingHorizontal: 4,
  },
  syncLabel: {
    fontSize: 12,
    color: '#6b7280',
  },
  syncTime: {
    fontSize: 12,
    fontWeight: '500',
    color: '#1f2937',
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metricItem: {
    backgroundColor: '#f9fafb',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    width: '30%',
    minWidth: 80,
  },
  metricLabel: {
    fontSize: 10,
    color: '#6b7280',
    marginTop: 4,
    marginBottom: 2,
  },
  metricValue: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1f2937',
  },
});
