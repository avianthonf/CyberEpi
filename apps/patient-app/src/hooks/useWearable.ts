import { useState, useEffect } from 'react';
import { Platform } from 'react-native';
import Health, {
  HealthKitPermissions,
  HealthValue,
  HealthUnit,
} from 'react-native-health';
import { connect, connectToSources, disconnect, initialize } from 'react-native-health-connect';
import { MMKV } from 'react-native-mmkv';
import { WearableData } from '@/types';

// Storage for wearable data
const wearableStorage = new MMKV({
  id: 'wearable-storage',
  encryptionKey: 'wearable-encryption-key',
});

interface UseWearableOptions {
  enabled?: boolean;
  pollInterval?: number; // minutes
}

export function useWearable(options: UseWearableOptions = {}) {
  const { enabled = true, pollInterval = 30 } = options;
  const [wearableData, setWearableData] = useState<WearableData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAuthorized, setIsAuthorized] = useState(false);

  // Initialize HealthKit (iOS)
  const initializeHealthKit = async () => {
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

      const isAuthorized = await Health.initHealthKit(permissions, null);
      setIsAuthorized(isAuthorized);
      
      if (isAuthorized) {
        await fetchHealthKitData();
      }
    } catch (err) {
      console.error('HealthKit initialization error:', err);
      setError('Failed to initialize HealthKit');
    }
  };

  // Initialize Health Connect (Android)
  const initializeHealthConnect = async () => {
    if (Platform.OS !== 'android') return;

    try {
      const isInitialized = await initialize();
      if (!isInitialized) {
        throw new Error('Failed to initialize Health Connect');
      }

      // Check permissions
      const hasPermissions = await checkHealthConnectPermissions();
      if (hasPermissions) {
        await fetchHealthConnectData();
      }
    } catch (err) {
      console.error('Health Connect initialization error:', err);
      setError('Failed to initialize Health Connect');
    }
  };

  // Check Health Connect permissions
  const checkHealthConnectPermissions = async () => {
    if (Platform.OS !== 'android') return false;

    try {
      const result = await connect();
      setIsAuthorized(result);
      return result;
    } catch (err) {
      console.error('Health Connect permission check:', err);
      return false;
    }
  };

  // Request Health Connect permissions
  const requestHealthConnectPermissions = async () => {
    if (Platform.OS !== 'android') return false;

    try {
      const result = await connectToSources([
        { dataType: 'HeartRate', accessType: 'read' },
        { dataType: 'HeartRateVariability', accessType: 'read' },
        { dataType: 'OxygenSaturation', accessType: 'read' },
        { dataType: 'Sleep', accessType: 'read' },
        { dataType: 'Steps', accessType: 'read' },
        { dataType: 'RestingHeartRate', accessType: 'read' },
      ]);
      
      setIsAuthorized(result);
      if (result) {
        await fetchHealthConnectData();
      }
      return result;
    } catch (err) {
      console.error('Health Connect permission request:', err);
      setError('Failed to request permissions');
      return false;
    }
  };

  // Fetch data from HealthKit
  const fetchHealthKitData = async () => {
    if (Platform.OS !== 'ios' || !isAuthorized) return;

    setIsLoading(true);
    setError(null);

    try {
      const now = new Date();
      const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

      const data: WearableData = {
        hrv_rmssd_ms: null,
        resting_hr_bpm: null,
        sleep_hours: null,
        step_count: null,
        spo2_pct: null,
        heart_rate_bpm: null,
        last_updated: new Date().toISOString(),
      };

      // Fetch HRV
      try {
        const hrvResults: HealthValue[] = await Health.getHrvSamples(
          yesterday.toISOString(),
          now.toISOString(),
          undefined,
          HealthUnit.beatsPerMinute
        );
        
        if (hrvResults.length > 0) {
          // Get the latest HRV value
          const latestHrv = hrvResults[hrvResults.length - 1];
          data.hrv_rmssd_ms = latestHrv.value;
        }
      } catch (err) {
        console.warn('Failed to fetch HRV:', err);
      }

      // Fetch Resting Heart Rate
      try {
        const restingHrResults: HealthValue[] = await Health.getRestingHeartRate(
          yesterday.toISOString(),
          now.toISOString(),
          undefined,
          HealthUnit.beatsPerMinute
        );
        
        if (restingHrResults.length > 0) {
          const latestRestingHr = restingHrResults[restingHrResults.length - 1];
          data.resting_hr_bpm = Math.round(latestRestingHr.value);
        }
      } catch (err) {
        console.warn('Failed to fetch resting heart rate:', err);
      }

      // Fetch Sleep
      try {
        const sleepResults = await Health.getSleepSamples(
          yesterday.toISOString(),
          now.toISOString(),
          undefined
        );
        
        if (sleepResults.length > 0) {
          // Calculate total sleep duration
          const totalSleepMs = sleepResults.reduce((total, sample) => {
            if (sample.value === Health.Constants.SleepAnalysis.Asleep) {
              return total + (sample.endDate.getTime() - sample.startDate.getTime());
            }
            return total;
          }, 0);
          
          data.sleep_hours = Math.round((totalSleepMs / (1000 * 60 * 60)) * 10) / 10;
        }
      } catch (err) {
        console.warn('Failed to fetch sleep data:', err);
      }

      // Fetch Steps
      try {
        const stepResults = await Health.getDailyStepCountSamples(
          yesterday.toISOString(),
          now.toISOString(),
          undefined
        );
        
        if (stepResults.length > 0) {
          data.step_count = stepResults.reduce((total, sample) => total + (sample.value || 0), 0);
        }
      } catch (err) {
        console.warn('Failed to fetch steps:', err);
      }

      // Fetch Oxygen Saturation
      try {
        const spo2Results: HealthValue[] = await Health.getOxygenSaturationSamples(
          yesterday.toISOString(),
          now.toISOString(),
          undefined,
          HealthUnit.percent
        );
        
        if (spo2Results.length > 0) {
          const latestSpo2 = spo2Results[spo2Results.length - 1];
          data.spo2_pct = Math.round(latestSpo2.value);
        }
      } catch (err) {
        console.warn('Failed to fetch SpO2:', err);
      }

      // Fetch latest Heart Rate
      try {
        const hrResults: HealthValue[] = await Health.getHeartRateSamples(
          yesterday.toISOString(),
          now.toISOString(),
          undefined,
          HealthUnit.beatsPerMinute
        );
        
        if (hrResults.length > 0) {
          const latestHr = hrResults[hrResults.length - 1];
          data.heart_rate_bpm = Math.round(latestHr.value);
        }
      } catch (err) {
        console.warn('Failed to fetch heart rate:', err);
      }

      // Cache the data
      wearableStorage.set('latest_data', JSON.stringify(data));
      setWearableData(data);
    } catch (err) {
      console.error('Error fetching HealthKit data:', err);
      setError('Failed to fetch health data');
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch data from Health Connect
  const fetchHealthConnectData = async () => {
    if (Platform.OS !== 'android' || !isAuthorized) return;

    setIsLoading(true);
    setError(null);

    try {
      const now = new Date();
      const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

      const data: WearableData = {
        hrv_rmssd_ms: null,
        resting_hr_bpm: null,
        sleep_hours: null,
        step_count: null,
        spo2_pct: null,
        heart_rate_bpm: null,
        last_updated: new Date().toISOString(),
      };

      // Note: Health Connect API implementation would go here
      // This is a placeholder as the actual implementation depends on the specific library version
      // and API endpoints available

      // Cache the data
      wearableStorage.set('latest_data', JSON.stringify(data));
      setWearableData(data);
    } catch (err) {
      console.error('Error fetching Health Connect data:', err);
      setError('Failed to fetch health data');
    } finally {
      setIsLoading(false);
    }
  };

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
  }, [enabled]);

  // Set up polling
  useEffect(() => {
    if (!enabled || !isAuthorized) return;

    const interval = setInterval(() => {
      if (Platform.OS === 'ios') {
        fetchHealthKitData();
      } else if (Platform.OS === 'android') {
        fetchHealthConnectData();
      }
    }, pollInterval * 60 * 1000);

    return () => clearInterval(interval);
  }, [enabled, isAuthorized, pollInterval]);

  // Request permissions function
  const requestPermissions = async () => {
    if (Platform.OS === 'ios') {
      // HealthKit permissions are requested during initialization
      await initializeHealthKit();
    } else if (Platform.OS === 'android') {
      await requestHealthConnectPermissions();
    }
  };

  // Disconnect function
  const disconnectWearable = async () => {
    if (Platform.OS === 'android') {
      try {
        await disconnect();
        setIsAuthorized(false);
      } catch (err) {
        console.error('Failed to disconnect Health Connect:', err);
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
