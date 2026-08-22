import {useState, useEffect, useCallback} from 'react';
import {Platform} from 'react-native';
import Health, {HealthKitPermissions} from 'react-native-health';
import * as HealthConnect from 'react-native-health-connect';
import {MMKV} from 'react-native-mmkv';
import {WearableData} from '@/types';
import {MMKV_ENCRYPTION_KEY} from '@/lib/storage';

// Storage for wearable data — same hardware-backed, per-device key as the
// rest of the app's encrypted MMKV stores.
const wearableStorage = new MMKV({
  id: 'wearable-storage',
  encryptionKey: MMKV_ENCRYPTION_KEY,
});

interface UseWearableOptions {
  enabled?: boolean;
  pollInterval?: number; // minutes
}

// Factory (not a module-level const) so last_updated is never a stale
// import-time timestamp.
const emptyData = (): WearableData => ({
  hrv_rmssd_ms: null,
  resting_hr_bpm: null,
  sleep_hours: null,
  step_count: null,
  spo2_pct: null,
  heart_rate_bpm: null,
  last_updated: new Date().toISOString(),
});

export function useWearable(options: UseWearableOptions = {}) {
  const {enabled = true, pollInterval = 30} = options;
  const [wearableData, setWearableData] = useState<WearableData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAuthorized, setIsAuthorized] = useState(false);

  const finishFetch = useCallback((data: WearableData) => {
    wearableStorage.set('latest_data', JSON.stringify(data));
    setWearableData(data);
    setIsLoading(false);
  }, []);

  // Fetch data from HealthKit (iOS) — callback-based API.
  const fetchHealthKitData = useCallback(() => {
    if (Platform.OS !== 'ios' || !isAuthorized) return;

    setIsLoading(true);
    setError(null);

    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const queryOptions = {
      startDate: yesterday.toISOString(),
      endDate: now.toISOString(),
      includeManuallyAdded: false,
    };

    const data: WearableData = {
      ...emptyData(),
      last_updated: now.toISOString(),
    };

    // Each read is guarded; failures leave the field null rather than
    // fabricating a value.
    Health.getHeartRateSamples(queryOptions, (err, results) => {
      if (!err && results.length > 0) {
        const latest = results[results.length - 1];
        if (latest) data.heart_rate_bpm = Math.round(latest.value);
      }
      finishFetch(data);
    });
  }, [isAuthorized, finishFetch]);

  // Fetch data from Health Connect (Android)
  const fetchHealthConnectData = useCallback(async () => {
    if (Platform.OS !== 'android' || !isAuthorized) return;

    setIsLoading(true);
    setError(null);

    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const timeRangeFilter = {
      operator: 'between' as const,
      startTime: yesterday.toISOString(),
      endTime: now.toISOString(),
    };

    const data: WearableData = {
      ...emptyData(),
      last_updated: now.toISOString(),
    };

    try {
      const steps = await HealthConnect.readRecords('Steps', {timeRangeFilter});
      data.step_count = steps.reduce((total, r) => total + r.count, 0);
    } catch (err) {
      console.warn('Failed to fetch steps from Health Connect:', err);
    }

    try {
      const heartRates = await HealthConnect.readRecords('HeartRate', {
        timeRangeFilter,
      });
      const last = heartRates.at(-1)?.samples.at(-1)?.beatsPerMinute;
      if (last) data.heart_rate_bpm = Math.round(last);
    } catch (err) {
      console.warn('Failed to fetch heart rate from Health Connect:', err);
    }

    finishFetch(data);
  }, [isAuthorized, finishFetch]);

  // Check Health Connect permissions
  const checkHealthConnectPermissions = useCallback(async () => {
    if (Platform.OS !== 'android') return false;

    try {
      const granted = await HealthConnect.getGrantedPermissions();
      setIsAuthorized(granted.length > 0);
      return granted.length > 0;
    } catch (err) {
      console.error('Health Connect permission check:', err);
      return false;
    }
  }, []);

  // Initialize HealthKit (iOS)
  const initializeHealthKit = useCallback(async () => {
    if (Platform.OS !== 'ios') return;

    try {
      const permissions: HealthKitPermissions = {
        permissions: {
          read: [
            Health.Constants.Permissions.HeartRate,
            Health.Constants.Permissions.HeartRateVariability,
            Health.Constants.Permissions.OxygenSaturation,
            Health.Constants.Permissions.SleepAnalysis,
            Health.Constants.Permissions.StepCount,
            Health.Constants.Permissions.RestingHeartRate,
          ],
          write: [],
        },
      };

      Health.initHealthKit(permissions, err => {
        if (err) {
          console.error('HealthKit initialization error:', err);
          setError('Failed to initialize HealthKit');
          setIsAuthorized(false);
          return;
        }
        setIsAuthorized(true);
        fetchHealthKitData();
      });
    } catch (err) {
      console.error('HealthKit initialization error:', err);
      setError('Failed to initialize HealthKit');
    }
  }, [fetchHealthKitData]);

  // Initialize Health Connect (Android)
  const initializeHealthConnect = useCallback(async () => {
    if (Platform.OS !== 'android') return;

    try {
      // Health Connect requires the system app + user permission. If the SDK
      // isn't available on the device, report unsupported rather than
      // fabricating data.
      const sdkStatus = await HealthConnect.getSdkStatus();
      if (sdkStatus !== 2) {
        setError('Health Connect is not available on this device');
        setIsAuthorized(false);
        return;
      }

      await HealthConnect.initialize();
      const hasPermissions = await checkHealthConnectPermissions();
      if (hasPermissions) {
        await fetchHealthConnectData();
      }
    } catch (err) {
      console.error('Health Connect initialization error:', err);
      setError('Failed to initialize Health Connect');
      setIsAuthorized(false);
    }
  }, [checkHealthConnectPermissions, fetchHealthConnectData]);

  // Request Health Connect permissions
  const requestHealthConnectPermissions = useCallback(async () => {
    if (Platform.OS !== 'android') return false;

    try {
      await HealthConnect.requestPermission([
        {accessType: 'read', recordType: 'HeartRate'},
        {accessType: 'read', recordType: 'OxygenSaturation'},
        {accessType: 'read', recordType: 'SleepSession'},
        {accessType: 'read', recordType: 'Steps'},
        {accessType: 'read', recordType: 'RestingHeartRate'},
      ]);
      setIsAuthorized(true);
      await fetchHealthConnectData();
      return true;
    } catch (err) {
      console.error('Health Connect permission request:', err);
      setError('Failed to request permissions');
      return false;
    }
  }, [fetchHealthConnectData]);

  // Load cached data on mount
  useEffect(() => {
    const cachedData = wearableStorage.getString('latest_data');
    if (cachedData) {
      try {
        const parsed: WearableData = JSON.parse(cachedData);
        setWearableData(parsed);
      } catch (err) {
        console.error('Failed to parse cached wearable data:', err);
      }
    }
  }, []);

  // Initialize on mount
  useEffect(() => {
    if (!enabled) return;

    if (Platform.OS === 'ios') {
      initializeHealthKit();
    } else if (Platform.OS === 'android') {
      initializeHealthConnect();
    }
  }, [enabled, initializeHealthKit, initializeHealthConnect]);

  // Set up polling
  useEffect(() => {
    if (!enabled || !isAuthorized) return;

    const interval = setInterval(
      () => {
        if (Platform.OS === 'ios') {
          fetchHealthKitData();
        } else if (Platform.OS === 'android') {
          fetchHealthConnectData();
        }
      },
      pollInterval * 60 * 1000,
    );

    return () => clearInterval(interval);
  }, [
    enabled,
    isAuthorized,
    pollInterval,
    fetchHealthKitData,
    fetchHealthConnectData,
  ]);

  // Request permissions function
  const requestPermissions = async () => {
    if (Platform.OS === 'ios') {
      await initializeHealthKit();
    } else if (Platform.OS === 'android') {
      await requestHealthConnectPermissions();
    }
  };

  // Disconnect function
  const disconnectWearable = async () => {
    if (Platform.OS === 'android') {
      try {
        await HealthConnect.revokeAllPermissions();
        setIsAuthorized(false);
      } catch (err) {
        console.error('Failed to revoke Health Connect permissions:', err);
      }
    }
  };

  return {
    wearableData,
    isLoading,
    error,
    isAuthorized,
    requestPermissions,
    refreshData: () => {
      if (Platform.OS === 'ios') {
        fetchHealthKitData();
      } else if (Platform.OS === 'android') {
        fetchHealthConnectData();
      }
    },
    disconnect: disconnectWearable,
  };
}
