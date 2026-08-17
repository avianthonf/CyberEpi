import { MMKV } from 'react-native-mmkv';

// Single shared MMKV instance for all app storage (offline queues, caches,
// wearable data, persisted stores).
const mmkv = new MMKV({
  id: 'cyberepi-storage',
  encryptionKey: process.env.EXPO_PUBLIC_MMKV_ENCRYPTION_KEY || 'cyberepi-storage-key',
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
