import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import {Platform} from 'react-native';
import {apiClient} from '@/services/api';
import {NotificationType} from '@/types';

// Configure notification handler
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export type NotificationRoute =
  | {screen: 'Home'}
  | {screen: 'Medications'}
  | {screen: 'RiskDetail'; patientId: string}
  | {screen: 'Alerts'};

export class NotificationService {
  private static instance: NotificationService;
  private pushToken: string | null = null;
  /**
   * Optional navigator callback. Consumers (typically the App root) wire
   * this to their navigator's `navigate` so notification taps actually go
   * somewhere. When unset the response handler is a no-op, not a TODO.
   */
  private navigator: ((route: NotificationRoute) => void) | null = null;

  setNavigator(nav: (route: NotificationRoute) => void) {
    this.navigator = nav;
  }

  static getInstance(): NotificationService {
    if (!NotificationService.instance) {
      NotificationService.instance = new NotificationService();
    }
    return NotificationService.instance;
  }

  // Request permissions
  async requestPermissions(): Promise<boolean> {
    if (Device.isDevice) {
      const {status: existingStatus} =
        await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      if (existingStatus !== 'granted') {
        const {status} = await Notifications.requestPermissionsAsync();
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
        await Notifications.setNotificationChannelAsync('default', {
          name: 'default',
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#FF231F7C',
        });
      }

      // The backend delivers through FCM/APNs directly, not Expo's relay.
      const deviceToken = await Notifications.getDevicePushTokenAsync();
      if (typeof deviceToken.data !== 'string') {
        throw new Error('Unsupported native push token format');
      }
      this.pushToken = deviceToken.data;
      return deviceToken.data;
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
        token: token,
        platform: Platform.OS,
      });
    } catch (error) {
      console.error('Failed to register push token:', error);
      throw error;
    }
  }

  // Deregister push token from backend - called during logout to prevent
  // cross-patient notification delivery when the device switches accounts.
  async deregisterPushToken(): Promise<void> {
    try {
      const token = this.pushToken;
      if (!token) {
        // No token to deregister
        return;
      }
      await apiClient.delete(`/patients/me/push_token`, {
        token,
        platform: Platform.OS,
      });
    } catch (error) {
      console.error('Failed to deregister push token:', error);
      throw error;
    }
  }

  // Schedule local notification
  async scheduleLocalNotification(
    title: string,
    body: string,
    data?: Record<string, unknown>,
    trigger?: Notifications.NotificationTriggerInput,
  ): Promise<string> {
    try {
      return await Notifications.scheduleNotificationAsync({
        content: {
          title,
          body,
          data: data || {},
          sound: 'default',
        },
        trigger: trigger || null,
      });
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
    repeat: boolean = true,
  ): Promise<string> {
    const parts = time.split(':');
    const hours = Number(parts[0]);
    const minutes = Number(parts[1]);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
      throw new Error(`Invalid reminder time: ${time}`);
    }

    const trigger: Notifications.NotificationTriggerInput = {
      hour: hours,
      minute: minutes,
      repeats: repeat,
    };

    return this.scheduleLocalNotification(
      'Medication Reminder',
      `Time to take ${medicationName}`,
      {type: 'MEDICATION_REMINDER', medicationId},
      trigger,
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
  async getScheduledNotifications(): Promise<
    Notifications.NotificationRequest[]
  > {
    try {
      return await Notifications.getAllScheduledNotificationsAsync();
    } catch (error) {
      console.error('Failed to get scheduled notifications:', error);
      return [];
    }
  }

  // Handle notification response — routes to the registered screen via the
  // navigator callback set by App.tsx. Without a navigator this is a no-op.
  handleNotificationResponse = (
    response: Notifications.NotificationResponse,
  ) => {
    const nav = this.navigator;
    if (!nav) {
      return;
    }
    const {notification} = response;
    const data = (notification.request.content.data || {}) as Record<
      string,
      unknown
    >;
    const type = data.type as NotificationType | undefined;
    switch (type) {
      case 'RISK_CHANGE':
        nav({screen: 'RiskDetail', patientId: String(data.patient_id ?? '')});
        return;
      case 'MEDICATION_REMINDER':
        nav({screen: 'Medications'});
        return;
      case 'EXPOSURE_ALERT':
        nav({screen: 'Alerts'});
        return;
      default:
        nav({screen: 'Home'});
        return;
    }
  };

  // Initialize notification listeners
  initializeListeners(): void {
    // Handle notification when app is in foreground
    Notifications.addNotificationReceivedListener(notification => {
      console.log('Notification received in foreground:', notification);
    });

    // Handle notification response (user taps notification)
    Notifications.addNotificationResponseReceivedListener(
      this.handleNotificationResponse,
    );
  }

  // Send test notification (for development)
  async sendTestNotification(): Promise<void> {
    try {
      await this.scheduleLocalNotification(
        'Test Notification',
        'This is a test notification from CyberEpi',
        {type: 'TEST'},
      );
    } catch (error) {
      console.error('Failed to send test notification:', error);
    }
  }
}

export const notificationService = NotificationService.getInstance();

// Setup function to be called on app start
export async function setupNotifications(userId?: string): Promise<void> {
  try {
    // Initialize listeners
    notificationService.initializeListeners();

    // Get and store push token
    await notificationService.getPushToken();

    // Register with backend if authenticated
    if (userId) {
      await notificationService.registerPushToken(userId);
    }

    console.log('Notifications initialized successfully');
  } catch (error) {
    console.error('Failed to setup notifications:', error);
  }
}
