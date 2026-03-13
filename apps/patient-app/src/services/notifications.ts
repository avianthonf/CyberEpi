import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import { apiClient } from '@/services/api';
import { useAuthStore } from '@/store/authStore';
import { NotificationType } from '@/types';

// Configure notification handler
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export class NotificationService {
  private static instance: NotificationService;
  private pushToken: string | null = null;

  static getInstance(): NotificationService {
    if (!NotificationService.instance) {
      NotificationService.instance = new NotificationService();
    }
    return NotificationService.instance;
  }

  // Request permissions
  async requestPermissions(): Promise<boolean> {
    if (Device.isDevice) {
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;
      
      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }
      
      if (finalStatus !== 'granted') {
        console.log('Failed to get push token for push notification!');
        return false;
      }
      
      return true;
    } else {
      console.log('Must use physical device for Push Notifications');
      return false;
    }
  }

  // Get push token
  async getPushToken(): Promise<string | null> {
    try {
      const hasPermission = await this.requestPermissions();
      if (!hasPermission) return null;

      if (Platform.OS === 'android') {
        Notifications.setNotificationChannelAsync('default', {
          name: 'default',
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#FF231F7C',
        });
      }

      const token = (await Notifications.getExpoPushTokenAsync({
        projectId: process.env.EXPO_PUBLIC_PROJECT_ID,
      })).data;
      
      this.pushToken = token;
      return token;
    } catch (error) {
      console.error('Failed to get push token:', error);
      return null;
    }
  }

  // Register push token with backend
  async registerPushToken(userId: string): Promise<void> {
    try {
      const token = await this.getPushToken();
      if (!token) {
        throw new Error('No push token available');
      }

      await apiClient.post(`/patients/${userId}/push_token`, {
        push_token: token,
        platform: Platform.OS,
      });
    } catch (error) {
      console.error('Failed to register push token:', error);
      throw error;
    }
  }

  // Schedule local notification
  async scheduleLocalNotification(
    title: string,
    body: string,
    data?: any,
    trigger?: Notifications.NotificationTriggerInput
  ): Promise<string> {
    try {
      const notificationId = await Notifications.scheduleNotificationAsync({
        content: {
          title,
          body,
          data: data || {},
          sound: 'default',
        },
        trigger: trigger || null,
      });
      
      return notificationId;
    } catch (error) {
      console.error('Failed to schedule notification:', error);
      throw error;
    }
  }

  // Schedule medication reminder
  async scheduleMedicationReminder(
    medicationId: string,
    medicationName: string,
    time: string,
    repeat: boolean = true
  ): Promise<string> {
    const [hours, minutes] = time.split(':').map(Number);
    
    const trigger: Notifications.NotificationTriggerInput = {
      hour: hours,
      minute: minutes,
      repeats: repeat,
    };

    return this.scheduleLocalNotification(
      'Medication Reminder',
      `Time to take ${medicationName}`,
      { type: 'MEDICATION_REMINDER', medicationId },
      trigger
    );
  }

  // Cancel notification
  async cancelNotification(notificationId: string): Promise<void> {
    try {
      await Notifications.cancelScheduledNotificationAsync(notificationId);
    } catch (error) {
      console.error('Failed to cancel notification:', error);
    }
  }

  // Cancel all notifications
  async cancelAllNotifications(): Promise<void> {
    try {
      await Notifications.cancelAllScheduledNotificationsAsync();
    } catch (error) {
      console.error('Failed to cancel all notifications:', error);
    }
  }

  // Get scheduled notifications
  async getScheduledNotifications(): Promise<Notifications.NotificationRequest[]> {
    try {
      return await Notifications.getAllScheduledNotificationsAsync();
    } catch (error) {
      console.error('Failed to get scheduled notifications:', error);
      return [];
    }
  }

  // Handle notification response
  handleNotificationResponse = (response: Notifications.NotificationResponse) => {
    const { notification } = response;
    const data = notification.request.content.data as NotificationType;

    switch (data) {
      case 'RISK_CHANGE':
        // Navigate to home screen
        break;
      case 'MEDICATION_REMINDER':
        // Navigate to medications screen
        break;
      case 'EXPOSURE_ALERT':
        // Navigate to home screen with alert
        break;
      default:
        // Default navigation
        break;
    }
  };

  // Initialize notification listeners
  initializeListeners(): void {
    // Handle notification when app is in foreground
    Notifications.addNotificationReceivedListener((notification) => {
      console.log('Notification received in foreground:', notification);
    });

    // Handle notification response (user taps notification)
    Notifications.addNotificationResponseReceivedListener(this.handleNotificationResponse);
  }

  // Send test notification (for development)
  async sendTestNotification(): Promise<void> {
    try {
      await this.scheduleLocalNotification(
        'Test Notification',
        'This is a test notification from CyberEpi',
        { type: 'TEST' }
      );
    } catch (error) {
      console.error('Failed to send test notification:', error);
    }
  }
}

export const notificationService = NotificationService.getInstance();

// Setup function to be called on app start
export async function setupNotifications(): Promise<void> {
  try {
    // Initialize listeners
    notificationService.initializeListeners();
    
    // Get and store push token
    await notificationService.getPushToken();
    
    console.log('Notifications initialized successfully');
  } catch (error) {
    console.error('Failed to setup notifications:', error);
  }
}
