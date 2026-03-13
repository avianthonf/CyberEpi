import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { useAuthStore } from '@/store/authStore';

export default function AuthLayout() {
  const { isAuthenticated, checkAuth } = useAuthStore();

  useEffect(() => {
    // Check authentication status on mount
    checkAuth();
  }, [checkAuth]);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="register" />
    </Stack>
  );
}
