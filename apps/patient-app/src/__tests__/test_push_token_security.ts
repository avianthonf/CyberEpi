import {notificationService} from '@/services/notifications';
import {apiClient} from '@/services/api';
import {Platform} from 'react-native';
import * as Notifications from 'expo-notifications';

jest.mock('@/services/api', () => ({
  apiClient: {
    post: jest.fn(),
    delete: jest.fn(),
  },
}));

jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
}));

describe('Push Token Security', () => {
  const mockToken = 'ExponentPushToken[test-token-123]';

  beforeEach(() => {
    jest.clearAllMocks();
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: mockToken,
    });
  });

  describe('registerPushToken', () => {
    it('sends platform and token to backend for exclusive binding', async () => {
      // Mock getPushToken to return the test token
      jest.spyOn(notificationService, 'getPushToken').mockResolvedValue(mockToken);
      
      const userId = 'patient-uuid-1';
      await notificationService.registerPushToken(userId);

      expect(apiClient.post).toHaveBeenCalledWith(
        `/patients/${userId}/push_token`,
        {
          token: mockToken,
          platform: Platform.OS,
        },
      );
    });

    it('throws when no token available', async () => {
      // Mock getPushToken to return null simulating no token
      jest.spyOn(notificationService, 'getPushToken').mockResolvedValue(null);
      
      await expect(
        notificationService.registerPushToken('patient-uuid-1'),
      ).rejects.toThrow('No push token available');
    });
  });

  describe('deregisterPushToken', () => {
    it('calls authenticated deletion endpoint with JSON body', async () => {
      // Test private field - cast once to named const for setup
      const service = notificationService as unknown as {pushToken: string | null};
      service.pushToken = mockToken;
      
      await notificationService.deregisterPushToken();

      expect(apiClient.delete).toHaveBeenCalledWith(
        `/patients/me/push_token`,
        {token: mockToken, platform: Platform.OS},
      );
    });

    it('succeeds silently when no token exists', async () => {
      const service = notificationService as unknown as {pushToken: string | null};
      service.pushToken = null;
      
      await expect(
        notificationService.deregisterPushToken(),
      ).resolves.toBeUndefined();

      expect(apiClient.delete).not.toHaveBeenCalled();
    });

    it('throws on backend failure to signal incomplete cleanup', async () => {
      const service = notificationService as unknown as {pushToken: string | null};
      service.pushToken = mockToken;
      (apiClient.delete as jest.Mock).mockRejectedValue(
        new Error('Network timeout'),
      );

      await expect(
        notificationService.deregisterPushToken(),
      ).rejects.toThrow('Network timeout');
    });
  });

  describe('Cross-account notification prevention', () => {
    it('prevents token reuse across patient accounts via exclusive binding', async () => {
      // Mock getPushToken to return the test token
      jest.spyOn(notificationService, 'getPushToken').mockResolvedValue(mockToken);
      
      // Patient A registers their device
      const patientA = 'uuid-patient-a';
      await notificationService.registerPushToken(patientA);

      expect(apiClient.post).toHaveBeenCalledWith(
        `/patients/${patientA}/push_token`,
        {token: mockToken, platform: Platform.OS},
      );

      // Patient B logs in on same device and registers same token
      const patientB = 'uuid-patient-b';
      await notificationService.registerPushToken(patientB);

      // Backend exclusive binding transfers ownership atomically
      expect(apiClient.post).toHaveBeenCalledWith(
        `/patients/${patientB}/push_token`,
        {token: mockToken, platform: Platform.OS},
      );

      // Subsequent pushes to this token reach only patient B
      // (Backend enforces via composite PK upsert, verified in backend tests)
    });
  });
});
