import React from 'react';
import {View, Text, StyleSheet, TouchableOpacity, Alert} from 'react-native';
import {RiskTier} from '@/types';
import {getRiskTierColor} from '@/store/riskStore';

interface AlertBannerProps {
  tier: RiskTier;
  message?: string;
  onCallPress?: () => void;
  onDismiss?: () => void;
  showCallButton?: boolean;
}

export function AlertBanner({
  tier,
  message,
  onCallPress,
  onDismiss,
  showCallButton = false,
}: AlertBannerProps) {
  const getAlertMessage = (riskTier: RiskTier): string => {
    switch (riskTier) {
      case 'low':
        return 'Your risk level is low. Continue monitoring your symptoms daily.';
      case 'moderate':
        return 'Your risk level is moderate. Please continue monitoring and consider consulting a physician if symptoms worsen.';
      case 'consult':
        return 'Your risk level requires medical consultation. Please consider scheduling an appointment with your physician.';
      case 'urgent':
        return 'Your risk level is urgent. Immediate medical attention is recommended.';
      default:
        return 'Unable to determine risk level. Please submit more symptom reports.';
    }
  };

  const handleCallPress = () => {
    if (onCallPress) {
      Alert.alert(
        'Emergency Call',
        'Your risk score indicates immediate medical attention is needed. Do you want to call the crisis line?',
        [
          {text: 'Cancel', style: 'cancel'},
          {text: 'Call Now', onPress: onCallPress},
        ],
        {cancelable: false},
      );
    }
  };

  if (tier === 'low') {
    return null; // Don't show banner for low risk
  }

  return (
    <View
      style={[
        styles.container,
        {backgroundColor: getRiskTierColor(tier)},
        tier === 'urgent' && styles.urgentContainer,
      ]}>
      <View style={styles.content}>
        <Text style={styles.alertTitle}>
          {tier === 'urgent'
            ? '⚠️ URGENT'
            : tier === 'consult'
              ? '⚡ Consult Required'
              : '⚠️ Elevated Risk'}
        </Text>
        <Text style={styles.alertMessage}>
          {message || getAlertMessage(tier)}
        </Text>

        {showCallButton && tier === 'urgent' && (
          <TouchableOpacity
            style={[styles.callButton, {backgroundColor: '#ffffff'}]}
            onPress={handleCallPress}
            activeOpacity={0.8}>
            <Text
              style={[styles.callButtonText, {color: getRiskTierColor(tier)}]}>
              CALL NOW
            </Text>
          </TouchableOpacity>
        )}

        {tier === 'consult' && (
          <TouchableOpacity
            style={[styles.consultButton, {backgroundColor: '#ffffff'}]}
            onPress={onDismiss}
            activeOpacity={0.8}>
            <Text
              style={[
                styles.consultButtonText,
                {color: getRiskTierColor(tier)},
              ]}>
              I Understand
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {onDismiss && tier !== 'urgent' && (
        <TouchableOpacity style={styles.dismissButton} onPress={onDismiss}>
          <Text style={styles.dismissText}>✕</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 8,
    padding: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  urgentContainer: {
    // Additional styling for urgent alerts
    borderWidth: 2,
    borderColor: '#ffffff',
  },
  content: {
    flex: 1,
  },
  alertTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#ffffff',
    marginBottom: 8,
  },
  alertMessage: {
    fontSize: 14,
    color: '#ffffff',
    lineHeight: 20,
    marginBottom: 12,
  },
  callButton: {
    alignSelf: 'flex-start',
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
    marginTop: 8,
  },
  callButtonText: {
    fontSize: 14,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
  consultButton: {
    alignSelf: 'flex-start',
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 16,
    marginTop: 8,
  },
  consultButtonText: {
    fontSize: 12,
    fontWeight: '600',
  },
  dismissButton: {
    position: 'absolute',
    top: 12,
    right: 12,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dismissText: {
    fontSize: 16,
    color: '#ffffff',
    fontWeight: 'bold',
  },
});
