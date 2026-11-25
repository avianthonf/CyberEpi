import {useEffect} from 'react';
import {Stack} from 'expo-router';
import {StatusBar} from 'expo-status-bar';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '@/lib/queryClient';
import {useAuthStore} from '@/store/authStore';
import {useNetworkSync} from '@/hooks/useRiskScore';
import {setupNotifications} from '@/services/notifications';

function RootNavigator() {
  const {isAuthenticated, checkAuth, sessionGeneration} = useAuthStore();

  // Initialize network sync
  useNetworkSync();

  useEffect(() => {
    // Check authentication on app start
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    // Initialize push notifications after authentication
    const userId = isAuthenticated ? useAuthStore.getState().user?.id : undefined;
    setupNotifications(userId).catch(() => {
      console.warn('Notification setup is temporarily unavailable.');
    });
  }, [isAuthenticated]);

  return (
    <>
      <StatusBar style="auto" />
      <Stack key={sessionGeneration} screenOptions={{headerShown: false}}>
        <Stack.Screen name="(auth)" redirect={isAuthenticated} />
        <Stack.Screen name="(tabs)" redirect={!isAuthenticated} />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <RootNavigator />
    </QueryClientProvider>
  );
}
