import {MMKV} from 'react-native-mmkv';
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const KEY_ALIAS = 'cyberepi-mmkv-key';

// The MMKV encryption key protects patient data cached offline (symptom
// history, medications, offline queues). It must be unique per device and
// hardware-backed: anything delivered through EXPO_PUBLIC_* env vars is
// compiled into the JS bundle and readable by anyone who unpacks the app,
// and a shared fallback key would decrypt every install's storage.
function loadOrCreateEncryptionKey(): string {
  const existing = SecureStore.getItem(KEY_ALIAS);
  if (existing) {
    return existing;
  }
  // 244 bits of entropy; stored in Keychain (iOS) / Keystore (Android).
  const generated = `${Crypto.randomUUID()}${Crypto.randomUUID()}`;
  SecureStore.setItem(KEY_ALIAS, generated);
  return generated;
}

// Load once at module start; SecureStore lookups hit the device keystore, so
// we avoid repeating them for every MMKV store that needs a key.
export const MMKV_ENCRYPTION_KEY = loadOrCreateEncryptionKey();

// Single shared MMKV instance for all app storage (offline queues, caches,
// wearable data, persisted stores)
export const mmkv = new MMKV({
  id: 'cyberepi-storage',
  encryptionKey: MMKV_ENCRYPTION_KEY,
});

export const mmkvStorage = {
  getItem: (name: string): string | null => {
    return mmkv.getString(name) ?? null;
  },
  setItem: (name: string, value: string): void => {
    mmkv.set(name, value);
  },
  removeItem: (name: string): void => {
    mmkv.delete(name);
  },
};

export default mmkv;
