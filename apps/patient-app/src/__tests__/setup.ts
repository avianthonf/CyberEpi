import 'react-native-gesture-handler/jestSetup';

// Silence the warning: Animated: `useNativeDriver` is not supported
jest.mock('react-native/Libraries/Animated/NativeAnimatedHelper');

// Mock expo-secure-store
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn(() => 'mock-storage-key'),
  setItem: jest.fn(),
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

jest.mock('expo-crypto', () => ({
  randomUUID: jest.fn(() => '00000000-0000-4000-8000-000000000000'),
}));

// MMKV mock
jest.mock('react-native-mmkv', () => ({
  MMKV: jest.fn().mockImplementation(() => ({
    set: jest.fn(),
    getString: jest.fn(),
    delete: jest.fn(),
    getNumber: jest.fn(),
    getBoolean: jest.fn(),
  })),
}));

// Mock expo-notifications
jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  requestPermissionsAsync: jest.fn(() => ({status: 'granted'})),
  getExpoPushTokenAsync: jest.fn(() => ({data: 'mock-token'})),
  scheduleNotificationAsync: jest.fn(() => 'mock-id'),
  cancelScheduledNotificationAsync: jest.fn(),
  cancelAllScheduledNotificationsAsync: jest.fn(),
  getAllScheduledNotificationsAsync: jest.fn(() => []),
  addNotificationReceivedListener: jest.fn(),
  addNotificationResponseReceivedListener: jest.fn(),
}));

// Mock expo-auth-session
jest.mock('expo-auth-session', () => ({
  AuthRequest: jest.fn().mockImplementation(() => ({
    promptAsync: jest.fn(() => ({
      type: 'success',
      params: {code: 'mock-code'},
    })),
  })),
  makeRedirectUri: jest.fn(() => 'https://mock-uri'),
  ResponseType: {Code: 'code'},
}));

// Mock expo-camera
jest.mock('expo-camera', () => ({
  requestCameraPermissionsAsync: jest.fn(() => ({status: 'granted'})),
}));

// Mock expo-image-picker
jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(() => ({status: 'granted'})),
  requestMediaLibraryPermissionsAsync: jest.fn(() => ({status: 'granted'})),
  launchCameraAsync: jest.fn(() => ({
    canceled: false,
    assets: [{uri: 'mock-image-uri'}],
  })),
  launchImageLibraryAsync: jest.fn(() => ({
    canceled: false,
    assets: [{uri: 'mock-image-uri'}],
  })),
}));

// Mock react-native-health
jest.mock('react-native-health', () => ({
  initHealthKit: jest.fn(() => Promise.resolve(true)),
  getHeartRateSamples: jest.fn(() => Promise.resolve([{value: 72}])),
  getHrvSamples: jest.fn(() => Promise.resolve([{value: 45}])),
  getOxygenSaturationSamples: jest.fn(() => Promise.resolve([{value: 98}])),
  getSleepSamples: jest.fn(() => Promise.resolve([{value: 'Asleep'}])),
  getDailyStepCountSamples: jest.fn(() => Promise.resolve([{value: 10000}])),
  getRestingHeartRate: jest.fn(() => Promise.resolve([{value: 60}])),
  Constants: {
    Permissions: {
      HeartRate: 'HeartRate',
      HeartRateVariability: 'HeartRateVariability',
      OxygenSaturation: 'OxygenSaturation',
      SleepAnalysis: 'SleepAnalysis',
      StepCount: 'StepCount',
      RestingHeartRate: 'RestingHeartRate',
    },
    SleepAnalysis: {
      Asleep: 'Asleep',
    },
  },
}));

// Mock react-native-health-connect
jest.mock('react-native-health-connect', () => ({
  initialize: jest.fn(() => Promise.resolve(true)),
  connect: jest.fn(() => Promise.resolve(true)),
  disconnect: jest.fn(() => Promise.resolve()),
  connectToSources: jest.fn(() => Promise.resolve(true)),
}));

// Mock @react-native-community/netinfo
jest.mock('@react-native-community/netinfo', () => ({
  fetch: jest.fn(() => Promise.resolve({isConnected: true})),
  addEventListener: jest.fn(() => jest.fn()),
}));

// Mock react-native-svg
jest.mock('react-native-svg', () => {
  const React = require('react');
  return {
    __esModule: true,
    default: (props: Record<string, unknown>) =>
      React.createElement('Svg', props),
    Svg: (props: Record<string, unknown>) => React.createElement('Svg', props),
    Path: (props: Record<string, unknown>) =>
      React.createElement('Path', props),
    Circle: (props: Record<string, unknown>) =>
      React.createElement('Circle', props),
    Defs: (props: Record<string, unknown>) =>
      React.createElement('Defs', props),
    LinearGradient: (props: Record<string, unknown>) =>
      React.createElement('LinearGradient', props),
    Stop: (props: Record<string, unknown>) =>
      React.createElement('Stop', props),
  };
});

// Mock react-native-reanimated
jest.mock('react-native-reanimated', () => {
  const Reanimated = require('react-native-reanimated/mock');
  Reanimated.default.call = () => {};
  return Reanimated;
});

// Mock expo-background-fetch
jest.mock('expo-background-fetch', () => ({
  registerTaskAsync: jest.fn(),
  unregisterTaskAsync: jest.fn(),
}));

// Global test utilities
global.console = {
  ...console,
  // Uncomment to ignore specific console logs during tests
  // log: jest.fn(),
  // debug: jest.fn(),
  // info: jest.fn(),
  // warn: jest.fn(),
  // error: jest.fn(),
};
