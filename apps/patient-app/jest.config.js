module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/src/__tests__/setup.ts'],
  testMatch: [
    '**/__tests__/**/!(*setup).ts',
    '**/__tests__/**/!(*setup).tsx',
    '**/*.(test|spec).(ts|tsx|js)',
  ],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/__tests__/**/*',
    '!src/**/*.stories.{ts,tsx}',
  ],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@/components/(.*)$': '<rootDir>/src/components/$1',
    '^@/hooks/(.*)$': '<rootDir>/src/hooks/$1',
    '^@/store/(.*)$': '<rootDir>/src/store/$1',
    '^@/services/(.*)$': '<rootDir>/src/services/$1',
    '^@/types/(.*)$': '<rootDir>/src/types/$1',
    '^@/utils/(.*)$': '<rootDir>/src/utils/$1',
  },
  transformIgnorePatterns: [
    'node_modules/(?!(jest-)?react-native|@react-native|expo|@expo|@react-navigation|react-native-svg|react-native-reanimated|react-native-gesture-handler|@tanstack/react-query|zustand)/',
  ],
};
