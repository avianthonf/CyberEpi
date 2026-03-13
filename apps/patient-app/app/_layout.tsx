import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '@/store/authStore';
import { useNetworkSync } from '@/hooks/useRiskScore';
import { setupNotifications } from '@/services/notifications';

export default function RootLayout() {
  const { isAuthenticated, checkAuth } = useAuthStore();
  
  // Initialize network sync
  useNetworkSync();

  useEffect(() => {
    // Check authentication on app start
    checkAuth();
    
    // Initialize push notifications
    setupNotifications().catch(console.error);
  }, [checkAuth]);

  return (
    <>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(auth)" redirect={isAuthenticated} />
        <Stack.Screen name="(tabs)" redirect={!isAuthenticated} />
      </Stack>
    </>
  );
}
