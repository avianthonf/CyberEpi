import React, {useState, useEffect, useRef} from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TextInput,
  Alert,
} from 'react-native';
import {useRouter} from 'expo-router';
import {useAuthStore} from '@/store/authStore';
import {apiClient} from '@/services/api';

interface RegisterFormData {
  email: string;
  password: string;
  confirmPassword: string;
  firstName: string;
  lastName: string;
}

interface RegisterResponse {
  id: string;
  keycloak_id: string;
  message: string;
}

interface ValidationError {
  loc: string[];
  msg: string;
  type: string;
}

interface ErrorResponse {
  detail: string | ValidationError[];
}

export default function RegisterScreen() {
  const router = useRouter();
  const {login, isLoading: authLoading, isAuthenticated} = useAuthStore();

  const [formData, setFormData] = useState<RegisterFormData>({
    email: '',
    password: '',
    confirmPassword: '',
    firstName: '',
    lastName: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Partial<RegisterFormData>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [accountCreated, setAccountCreated] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      router.replace('/(tabs)/home');
    }
  }, [isAuthenticated, router]);

  const validateForm = (): boolean => {
    const newErrors: Partial<RegisterFormData> = {};

    // Email validation
    const trimmedEmail = formData.email.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!trimmedEmail) {
      newErrors.email = 'Email is required';
    } else if (!emailRegex.test(trimmedEmail)) {
      newErrors.email = 'Invalid email format';
    } else if (trimmedEmail.length > 200) {
      newErrors.email = 'Email must be 200 characters or less';
    }

    // Password validation
    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    } else if (formData.password.length > 128) {
      newErrors.password = 'Password must be 128 characters or less';
    }

    // Confirm password validation
    if (!formData.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    // First name validation
    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    } else if (formData.firstName.length > 100) {
      newErrors.firstName = 'First name must be 100 characters or less';
    }

    // Last name validation
    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    } else if (formData.lastName.length > 100) {
      newErrors.lastName = 'Last name must be 100 characters or less';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const submissionInFlightRef = useRef(false);

  const handleRegister = async () => {
    if (!validateForm()) {
      return;
    }

    // Guard against duplicate submissions
    if (submissionInFlightRef.current) {
      return;
    }

    submissionInFlightRef.current = true;
    setIsSubmitting(true);
    setServerError(null);

    try {
      const response = await apiClient.post<RegisterResponse>(
        '/auth/register',
        {
          email: formData.email.trim(),
          password: formData.password,
          first_name: formData.firstName.trim(),
          last_name: formData.lastName.trim(),
          role: 'patient',
        },
      );

      if (response.status === 201) {
        // Clear password from memory
        setFormData(prev => ({
          ...prev,
          password: '',
          confirmPassword: '',
        }));

        setAccountCreated(true);
        Alert.alert(
          'Account Created',
          'Your account has been successfully created. Please sign in to continue.',
          [
            {
              text: 'Sign In',
              onPress: handleSignIn,
            },
          ],
        );
      }
    } catch (error: unknown) {
      // Do not log error - may contain sensitive data like passwords

      // Handle specific error cases
      if (
        error &&
        typeof error === 'object' &&
        'response' in error &&
        error.response &&
        typeof error.response === 'object'
      ) {
        const response = error.response as {
          status?: number;
          data?: ErrorResponse;
        };

        if (response.status === 409) {
          setServerError(
            'An account with this email already exists. Please sign in instead.',
          );
        } else if (response.status === 422) {
          // Pydantic validation errors
          const detail = response.data?.detail;
          if (typeof detail === 'string') {
            setServerError(detail);
          } else if (Array.isArray(detail)) {
            const messages = detail.map((e: ValidationError) => e.msg).join('. ');
            setServerError(messages);
          } else {
            setServerError('Invalid registration data. Please check your input.');
          }
        } else if (response.status === 502 || response.status === 503) {
          setServerError(
            'Registration service is temporarily unavailable. Please try again later.',
          );
        } else if (response.status === 400) {
          setServerError('Invalid registration data. Please check your input.');
        } else {
          setServerError(
            'Registration failed. Please check your connection and try again.',
          );
        }
      } else {
        setServerError(
          'Registration failed. Please check your connection and try again.',
        );
      }
    } finally {
      setIsSubmitting(false);
      submissionInFlightRef.current = false;
    }
  };

  const handleSignIn = async () => {
    try {
      await login();
      // Navigation handled by useEffect on auth state change
    } catch (err) {
      // Do not log auth errors - may contain sensitive data
      // Redirect to login page which will show authStore error
      router.push('/(auth)/login');
    }
  };

  const handleGoToLogin = () => {
    router.push('/(auth)/login');
  };

  const updateField = (field: keyof RegisterFormData, value: string) => {
    setFormData(prev => ({...prev, [field]: value}));
    // Clear field error on edit
    if (errors[field]) {
      setErrors(prev => ({...prev, [field]: undefined}));
    }
  };

  const isLoading = isSubmitting || authLoading;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.title}>Create Account</Text>
            <Text style={styles.subtitle}>Join CyberEpi Health Monitor</Text>
          </View>

          {/* Registration Form */}
          {!accountCreated ? (
            <View style={styles.form}>
              {/* First Name */}
              <View style={styles.inputGroup}>
                <Text style={styles.label}>First Name</Text>
                <TextInput
                  style={[styles.input, errors.firstName ? styles.inputError : null]}
                  value={formData.firstName}
                  onChangeText={value => updateField('firstName', value)}
                  placeholder="Enter your first name"
                  placeholderTextColor="#999"
                  autoCapitalize="words"
                  autoCorrect={false}
                  editable={!isLoading}
                />
                {errors.firstName && (
                  <Text style={styles.errorText}>{errors.firstName}</Text>
                )}
              </View>

              {/* Last Name */}
              <View style={styles.inputGroup}>
                <Text style={styles.label}>Last Name</Text>
                <TextInput
                  style={[styles.input, errors.lastName ? styles.inputError : null]}
                  value={formData.lastName}
                  onChangeText={value => updateField('lastName', value)}
                  placeholder="Enter your last name"
                  placeholderTextColor="#999"
                  autoCapitalize="words"
                  autoCorrect={false}
                  editable={!isLoading}
                />
                {errors.lastName && (
                  <Text style={styles.errorText}>{errors.lastName}</Text>
                )}
              </View>

              {/* Email */}
              <View style={styles.inputGroup}>
                <Text style={styles.label}>Email</Text>
                <TextInput
                  style={[styles.input, errors.email ? styles.inputError : null]}
                  value={formData.email}
                  onChangeText={value => updateField('email', value)}
                  placeholder="Enter your email"
                  placeholderTextColor="#999"
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="email"
                  editable={!isLoading}
                />
                {errors.email && (
                  <Text style={styles.errorText}>{errors.email}</Text>
                )}
              </View>

              {/* Password */}
              <View style={styles.inputGroup}>
                <Text style={styles.label}>Password</Text>
                <TextInput
                  style={[styles.input, errors.password ? styles.inputError : null]}
                  value={formData.password}
                  onChangeText={value => updateField('password', value)}
                  placeholder="Create a password (min 8 characters)"
                  placeholderTextColor="#999"
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="password-new"
                  editable={!isLoading}
                />
                {errors.password && (
                  <Text style={styles.errorText}>{errors.password}</Text>
                )}
              </View>

              {/* Confirm Password */}
              <View style={styles.inputGroup}>
                <Text style={styles.label}>Confirm Password</Text>
                <TextInput
                  style={[
                    styles.input,
                    errors.confirmPassword ? styles.inputError : null,
                  ]}
                  value={formData.confirmPassword}
                  onChangeText={value => updateField('confirmPassword', value)}
                  placeholder="Re-enter your password"
                  placeholderTextColor="#999"
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="password-new"
                  editable={!isLoading}
                />
                {errors.confirmPassword && (
                  <Text style={styles.errorText}>{errors.confirmPassword}</Text>
                )}
              </View>

              {/* Server Error */}
              {serverError && (
                <View style={styles.serverErrorContainer}>
                  <Text style={styles.serverErrorText}>{serverError}</Text>
                </View>
              )}

              {/* Register Button */}
              <TouchableOpacity
                style={[
                  styles.registerButton,
                  isLoading && styles.disabledButton,
                ]}
                onPress={handleRegister}
                disabled={isLoading}
                accessibilityRole="button"
                accessibilityLabel="Create account">
                {isLoading ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.registerButtonText}>Create Account</Text>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.successBox}>
              <Text style={styles.successTitle}>Account Created!</Text>
              <Text style={styles.successText}>
                Your account has been successfully created. Sign in to start
                monitoring your health.
              </Text>
              <TouchableOpacity
                style={styles.signInButton}
                onPress={handleSignIn}
                disabled={authLoading}
                accessibilityRole="button"
                accessibilityLabel="Sign in with Keycloak">
                {authLoading ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.signInButtonText}>
                    Sign In with Keycloak
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* Login Link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Already have an account?</Text>
            <TouchableOpacity onPress={handleGoToLogin}>
              <Text style={styles.loginLink}>Sign In</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    paddingTop: 60,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 40,
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#666666',
    textAlign: 'center',
  },
  form: {
    marginBottom: 24,
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333333',
    marginBottom: 8,
  },
  input: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    color: '#1a1a1a',
    backgroundColor: '#ffffff',
  },
  inputError: {
    borderColor: '#ef4444',
  },
  errorText: {
    fontSize: 12,
    color: '#ef4444',
    marginTop: 4,
  },
  serverErrorContainer: {
    backgroundColor: '#fef2f2',
    borderLeftWidth: 4,
    borderLeftColor: '#ef4444',
    padding: 12,
    marginBottom: 16,
    borderRadius: 4,
  },
  serverErrorText: {
    fontSize: 14,
    color: '#991b1b',
  },
  registerButton: {
    backgroundColor: '#2563eb',
    paddingVertical: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 8,
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  disabledButton: {
    backgroundColor: '#94a3b8',
    opacity: 0.7,
  },
  registerButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  successBox: {
    backgroundColor: '#f0fdf4',
    borderLeftWidth: 4,
    borderLeftColor: '#22c55e',
    padding: 20,
    marginBottom: 24,
    borderRadius: 8,
  },
  successTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#166534',
    marginBottom: 8,
  },
  successText: {
    fontSize: 14,
    color: '#15803d',
    marginBottom: 16,
    lineHeight: 20,
  },
  signInButton: {
    backgroundColor: '#2563eb',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  signInButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 24,
  },
  footerText: {
    fontSize: 14,
    color: '#666666',
    marginRight: 4,
  },
  loginLink: {
    fontSize: 14,
    color: '#2563eb',
    fontWeight: '600',
  },
});
