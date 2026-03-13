import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuthStore } from '@/store/authStore';

export default function RegisterScreen() {
  const router = useRouter();
  const { login, isLoading, isAuthenticated } = useAuthStore();

  useEffect(() => {
    // Redirect if already authenticated
    if (isAuthenticated) {
      router.replace('/(tabs)/home');
    }
  }, [isAuthenticated, router]);

  const handleRegister = async () => {
    try {
      // For registration, we'll use the same OAuth flow
      // The actual registration happens in Keycloak
      await login();
      // Navigation will happen in useEffect when isAuthenticated changes
    } catch (err) {
      console.error('Registration error:', err);
      // Error is handled by the store
    }
  };

  const handleLogin = () => {
    router.push('/(auth)/login');
  };

  const handleContactSupport = () => {
    // Open email or support page
    Linking.openURL('mailto:support@cyberepi.health?subject=Registration Help');
  };

  return (
    <KeyboardAvoidingView 
      style={styles.container} 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.content}>
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.title}>Create Account</Text>
            <Text style={styles.subtitle}>Join CyberEpi Health Monitor</Text>
          </View>

          {/* Registration Info */}
          <View style={styles.form}>
            <View style={styles.infoBox}>
              <Text style={styles.infoTitle}>How to Register</Text>
              <Text style={styles.infoText}>
                1. Click "Sign Up with Keycloak" below{'\n'}
                2. You'll be redirected to our secure authentication portal{'\n'}
                3. Click "Create Account" on the sign-in page{'\n'}
                4. Fill in your details and verify your email{'\n'}
                5. Return to the app and sign in
              </Text>
            </View>

            <View style={styles.requirementsBox}>
              <Text style={styles.requirementsTitle}>Requirements</Text>
              <Text style={styles.requirementsText}>
                • Valid email address{'\n'}
                • Mobile phone number for verification{'\n'}
                • Basic health information (optional)
              </Text>
            </View>

            <TouchableOpacity 
              style={[styles.registerButton, isLoading && styles.disabledButton]}
              onPress={handleRegister}
              disabled={isLoading}
            >
              {isLoading ? (
                <ActivityIndicator color="#ffffff" size="small" />
              ) : (
                <Text style={styles.registerButtonText}>Sign Up with Keycloak</Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Login Link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Already have an account?</Text>
            <TouchableOpacity onPress={handleLogin}>
              <Text style={styles.loginLink}>Sign In</Text>
            </TouchableOpacity>
          </View>

          {/* Support */}
          <View style={styles.support}>
            <Text style={styles.supportText}>Need help?</Text>
            <TouchableOpacity onPress={handleContactSupport}>
              <Text style={styles.supportLink}>Contact Support</Text>
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
    paddingVertical: 60,
    justifyContent: 'space-between',
  },
  header: {
    alignItems: 'center',
    marginBottom: 40,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#6b7280',
    fontWeight: '500',
  },
  form: {
    flex: 1,
    justifyContent: 'center',
    maxWidth: 400,
    width: '100%',
    alignSelf: 'center',
  },
  infoBox: {
    backgroundColor: '#eff6ff',
    padding: 20,
    borderRadius: 12,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  infoTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1e40af',
    marginBottom: 12,
  },
  infoText: {
    fontSize: 14,
    color: '#1e40af',
    lineHeight: 20,
  },
  requirementsBox: {
    backgroundColor: '#f0fdf4',
    padding: 20,
    borderRadius: 12,
    marginBottom: 32,
    borderWidth: 1,
    borderColor: '#bbf7d0',
  },
  requirementsTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#166534',
    marginBottom: 12,
  },
  requirementsText: {
    fontSize: 14,
    color: '#166534',
    lineHeight: 20,
  },
  registerButton: {
    backgroundColor: '#10b981',
    paddingVertical: 16,
    paddingHorizontal: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  disabledButton: {
    backgroundColor: '#9ca3af',
    shadowOpacity: 0,
    elevation: 0,
  },
  registerButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    alignItems: 'center',
    marginTop: 40,
  },
  footerText: {
    fontSize: 14,
    color: '#6b7280',
  },
  loginLink: {
    fontSize: 14,
    color: '#3b82f6',
    fontWeight: '600',
    marginTop: 4,
  },
  support: {
    alignItems: 'center',
    marginTop: 20,
  },
  supportText: {
    fontSize: 12,
    color: '#9ca3af',
  },
  supportLink: {
    fontSize: 12,
    color: '#6b7280',
    fontWeight: '600',
    marginTop: 4,
    textDecorationLine: 'underline',
  },
});
