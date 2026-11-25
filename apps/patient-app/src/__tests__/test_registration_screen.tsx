import React from 'react';
import {render, fireEvent, waitFor, screen} from '@testing-library/react-native';
import {Alert} from 'react-native';
import RegisterScreen from '../../app/(auth)/register';
import {useAuthStore} from '@/store/authStore';
import {apiClient} from '@/services/api';
import {useRouter} from 'expo-router';

// Mock dependencies
jest.mock('expo-router', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/store/authStore', () => ({
  useAuthStore: jest.fn(),
}));

jest.mock('@/services/api', () => ({
  apiClient: {
    post: jest.fn(),
  },
}));

// Mock Alert
jest.spyOn(Alert, 'alert');

describe('RegisterScreen', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
  };

  const mockAuthStore = {
    login: jest.fn(),
    isLoading: false,
    isAuthenticated: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (useAuthStore as unknown as jest.Mock).mockReturnValue(mockAuthStore);
  });

  describe('Invalid Data Correction', () => {
    it('shows validation error for invalid email and allows correction', async () => {
      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'invalid-email',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'ValidPass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'ValidPass123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(screen.getByText('Invalid email format')).toBeTruthy();
      });

      // Correct the email
      const emailInput = screen.getByPlaceholderText('Enter your email');
      fireEvent.changeText(emailInput, 'valid@example.com');

      await waitFor(() => {
        expect(screen.queryByText('Invalid email format')).toBeNull();
      });
    });

    it('shows error when passwords do not match', async () => {
      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'john@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'Password123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'Different123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(screen.getByText('Passwords do not match')).toBeTruthy();
      });
    });
  });

  describe('Duplicate Account (409)', () => {
    it('shows correctable error when account already exists', async () => {
      (apiClient.post as jest.Mock).mockRejectedValue({
        response: {
          status: 409,
          data: {
            detail:
              'An account with this email already exists. Please log in instead.',
          },
        },
      });

      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'existing@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'SecurePass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'SecurePass123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(
          screen.getByText(
            'An account with this email already exists. Please sign in instead.',
          ),
        ).toBeTruthy();
      });
    });
  });

  describe('Service Outage', () => {
    it('shows error when backend service unavailable', async () => {
      (apiClient.post as jest.Mock).mockRejectedValue({
        response: {
          status: 502,
          data: {detail: 'Keycloak registration failed'},
        },
      });

      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'john@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'SecurePass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'SecurePass123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(
          screen.getByText(
            'Registration service is temporarily unavailable. Please try again later.',
          ),
        ).toBeTruthy();
      });
    });
  });

  describe('Duplicate Click Prevention', () => {
    it('prevents duplicate submissions while request in flight', async () => {
      let resolvePost: (value: unknown) => void;
      const postPromise = new Promise(resolve => {
        resolvePost = resolve;
      });
      (apiClient.post as jest.Mock).mockReturnValue(postPromise);

      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'john@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'SecurePass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'SecurePass123!',
      );

      const submitButton = screen.getByRole('button', {name: 'Create account'});

      // First submission
      fireEvent.press(submitButton);

      // Immediate second click should be ignored
      fireEvent.press(submitButton);
      fireEvent.press(submitButton);

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledTimes(1);
      });

      resolvePost!({
        status: 201,
        data: {id: '123', keycloak_id: 'kc-123', message: 'Success'},
      });
    });
  });

  describe('Success Without Authentication', () => {
    it('transitions to success state without authenticated status', async () => {
      (apiClient.post as jest.Mock).mockResolvedValue({
        status: 201,
        data: {
          id: '123e4567-e89b-12d3-a456-426614174000',
          keycloak_id: 'kc-user-123',
          message: 'Patient registered successfully',
        },
      });

      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'john.doe@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'SecurePass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'SecurePass123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(screen.getByText('Account Created!')).toBeTruthy();
        expect(screen.getByText('Sign In with Keycloak')).toBeTruthy();
      });

      // Should not be authenticated yet
      expect(mockAuthStore.isAuthenticated).toBe(false);
    });
  });

  describe('PKCE Failure Visible', () => {
    it('redirects to login page if PKCE flow fails after account creation', async () => {
      (apiClient.post as jest.Mock).mockResolvedValue({
        status: 201,
        data: {
          id: '123e4567-e89b-12d3-a456-426614174000',
          keycloak_id: 'kc-user-123',
          message: 'Patient registered successfully',
        },
      });

      mockAuthStore.login.mockRejectedValue(new Error('PKCE failed'));

      render(<RegisterScreen />);

      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your first name'),
        'John',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your last name'),
        'Doe',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Enter your email'),
        'john@example.com',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Create a password (min 8 characters)'),
        'SecurePass123!',
      );
      fireEvent.changeText(
        screen.getByPlaceholderText('Re-enter your password'),
        'SecurePass123!',
      );

      fireEvent.press(screen.getByRole('button', {name: 'Create account'}));

      await waitFor(() => {
        expect(screen.getByText('Account Created!')).toBeTruthy();
      });

      // Press Sign In - should fail and redirect to login
      const signInButton = screen.getByRole('button', {
        name: 'Sign in with Keycloak',
      });
      fireEvent.press(signInButton);

      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/(auth)/login');
      });
    });
  });
});
