import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { View, Text, TouchableOpacity } from 'react-native';
import { useAuthStore } from '@/store/authStore';
import { useRiskStore } from '@/store/riskStore';
import { useMedicationStore } from '@/store/medicationStore';
import { useSymptomSubmit } from '@/hooks/useSymptomSubmit';
import { useEffect } from 'react';
import NetInfo from '@react-native-community/netinfo';

export default function TabLayout() {
  const { logout } = useAuthStore();
  const { clearRiskData } = useRiskStore();
  const { clearMedications } = useMedicationStore();
  const { getQueuedReportsCount, syncQueuedReports } = useSymptomSubmit();

  useEffect(() => {
    // Sync when coming back online
    const unsubscribe = NetInfo.addEventListener(state => {
      if (state.isConnected) {
        syncQueuedReports();
      }
    });

    return () => unsubscribe();
  }, [syncQueuedReports]);

  const handleLogout = async () => {
    await logout();
    clearRiskData();
    clearMedications();
  };

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#3b82f6',
        tabBarInactiveTintColor: '#9ca3af',
        tabBarStyle: {
          backgroundColor: '#ffffff',
          borderTopWidth: 1,
          borderTopColor: '#e5e7eb',
        },
        headerStyle: {
          backgroundColor: '#ffffff',
        },
        headerTintColor: '#1f2937',
        headerTitleStyle: {
          fontWeight: '600',
        },
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
          headerRight: () => {
            const queuedCount = getQueuedReportsCount();
            return (
              <TouchableOpacity
                onPress={handleLogout}
                style={{ marginRight: 16 }}
              >
                <Ionicons name="log-out-outline" size={24} color="#6b7280" />
                {queuedCount > 0 && (
                  <View
                    style={{
                      position: 'absolute',
                      top: -4,
                      right: -4,
                      backgroundColor: '#ef4444',
                      borderRadius: 8,
                      width: 16,
                      height: 16,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Text
                      style={{
                        color: '#ffffff',
                        fontSize: 10,
                        fontWeight: 'bold',
                      }}
                    >
                      {queuedCount > 9 ? '9+' : queuedCount}
                    </Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          },
        }}
      />
      <Tabs.Screen
        name="symptoms"
        options={{
          title: 'Symptoms',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="medical-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="medications"
        options={{
          title: 'Medications',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="medkit-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'History',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="time-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
