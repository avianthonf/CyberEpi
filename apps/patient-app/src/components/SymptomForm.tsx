import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { SymptomReport } from '@/types';
import { useWearable } from '@/hooks/useWearable';
import { useSymptomSubmit } from '@/hooks/useSymptomSubmit';
import { useAuthStore } from '@/store/authStore';

interface SymptomFormProps {
  onSubmit?: (report: SymptomReport) => void;
  onCancel?: () => void;
}

type FormStep = 1 | 2 | 3 | 4;

interface SegmentSelectorProps {
  values: string[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

// Simple segmented selector — replaces @react-native-community/segmented-control
// (whose packaged types are incompatible with strict TS).
function SegmentSelector({ values, selectedIndex, onSelect }: SegmentSelectorProps) {
  return (
    <View style={styles.segmentRow}>
      {values.map((value, index) => (
        <TouchableOpacity
          key={value}
          style={[styles.segmentOption, index === selectedIndex && styles.segmentOptionActive]}
          onPress={() => onSelect(index)}
        >
          <Text
            style={[
              styles.segmentText,
              index === selectedIndex && styles.segmentTextActive,
            ]}
          >
            {value}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

interface FormData {
  fever_celsius: number | null;
  fever_measured: boolean;
  spo2_pct: number | null;
  spo2_measured: boolean;
  cough_severity: 0 | 1 | 2 | 3;
  dyspnoea: boolean;
  fatigue_severity: 0 | 1 | 2 | 3;
  heart_rate_bpm: number | null;
  heart_rate_measured: boolean;
  sore_throat: boolean;
  diarrhoea: boolean;
  anosmia: boolean;
}

export function SymptomForm({ onSubmit, onCancel }: SymptomFormProps) {
  const [currentStep, setCurrentStep] = useState<FormStep>(1);
  const [formData, setFormData] = useState<FormData>({
    fever_celsius: null,
    fever_measured: false,
    spo2_pct: null,
    spo2_measured: false,
    cough_severity: 0,
    dyspnoea: false,
    fatigue_severity: 0,
    heart_rate_bpm: null,
    heart_rate_measured: false,
    sore_throat: false,
    diarrhoea: false,
    anosmia: false,
  });

  const { wearableData } = useWearable();
  const { submitReport, isSubmitting } = useSymptomSubmit();
  const { user } = useAuthStore();

  // Auto-populate wearable data when available
  useEffect(() => {
    if (wearableData) {
      setFormData(prev => ({
        ...prev,
        spo2_pct: prev.spo2_pct || wearableData.spo2_pct,
        heart_rate_bpm: prev.heart_rate_bpm || wearableData.heart_rate_bpm,
        heart_rate_measured: !!wearableData.heart_rate_bpm,
        spo2_measured: !!wearableData.spo2_pct,
      }));
    }
  }, [wearableData]);

  const validateStep = (step: FormStep): boolean => {
    switch (step) {
      case 1:
        // Temperature and SpO2 validation
        if (formData.fever_measured && formData.fever_celsius) {
          if (formData.fever_celsius < 35.0 || formData.fever_celsius > 42.0) {
            Alert.alert('Invalid Temperature', 'Temperature must be between 35.0°C and 42.0°C');
            return false;
          }
        }
        if (formData.spo2_measured && formData.spo2_pct) {
          if (formData.spo2_pct < 85 || formData.spo2_pct > 100) {
            Alert.alert('Invalid SpO2', 'SpO2 must be between 85% and 100%');
            return false;
          }
        }
        return true;

      case 2:
        // Respiratory symptoms - no validation needed
        return true;

      case 3:
        // GI and other symptoms - no validation needed
        return true;

      case 4:
        // Review - all data is already validated
        return true;

      default:
        return false;
    }
  };

  const handleNext = () => {
    if (validateStep(currentStep)) {
      if (currentStep < 4) {
        setCurrentStep((currentStep + 1) as FormStep);
      }
    }
  };

  const handlePrevious = () => {
    if (currentStep > 1) {
      setCurrentStep((currentStep - 1) as FormStep);
    }
  };

  const handleSubmit = async () => {
    if (!user?.id) {
      Alert.alert('Error', 'User not authenticated');
      return;
    }

    // Build the symptom list from the form's boolean/severity controls
    const symptoms: string[] = [];
    if (formData.fever_celsius !== null) symptoms.push('fever');
    if (formData.cough_severity > 0) symptoms.push('cough');
    if (formData.dyspnoea) symptoms.push('dyspnoea');
    if (formData.fatigue_severity > 0) symptoms.push('fatigue');
    if (formData.sore_throat) symptoms.push('sore_throat');
    if (formData.diarrhoea) symptoms.push('diarrhea');
    if (formData.anosmia) symptoms.push('anosmia');

    // Create final report in the backend's expected shape
    const report: SymptomReport = {
      patient_id: user.id,
      symptoms,
      heart_rate: formData.heart_rate_measured ? formData.heart_rate_bpm : null,
      spo2: formData.spo2_measured ? formData.spo2_pct : null,
      temperature: formData.fever_measured ? formData.fever_celsius : null,
    };

    try {
      await submitReport({ report });
      onSubmit?.(report);
    } catch (error) {
      console.error('Submit error:', error);
    }
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return <Step1 formData={formData} setFormData={setFormData} />;
      case 2:
        return <Step2 formData={formData} setFormData={setFormData} />;
      case 3:
        return <Step3 formData={formData} setFormData={setFormData} />;
      case 4:
        return <Step4 formData={formData} wearableData={wearableData} />;
      default:
        return null;
    }
  };

  return (
    <View style={styles.container}>
      {/* Progress Indicator */}
      <View style={styles.progressContainer}>
        {[1, 2, 3, 4].map((step) => (
          <View key={step} style={styles.progressStep}>
            <View
              style={[
                styles.progressDot,
                step <= currentStep && styles.progressDotActive,
              ]}
            >
              <Text
                style={[
                  styles.progressDotText,
                  step <= currentStep && styles.progressDotTextActive,
                ]}
              >
                {step}
              </Text>
            </View>
            {step < 4 && (
              <View
                style={[
                  styles.progressLine,
                  step < currentStep && styles.progressLineActive,
                ]}
              />
            )}
          </View>
        ))}
      </View>

      {/* Step Content */}
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {renderStep()}
      </ScrollView>

      {/* Navigation Buttons */}
      <View style={styles.footer}>
        <View style={styles.buttonRow}>
          {currentStep > 1 && (
            <TouchableOpacity
              style={[styles.button, styles.buttonSecondary]}
              onPress={handlePrevious}
              disabled={isSubmitting}
            >
              <Text style={styles.buttonSecondaryText}>Previous</Text>
            </TouchableOpacity>
          )}

          <View style={styles.spacer} />

          {onCancel && (
            <TouchableOpacity
              style={[styles.button, styles.buttonCancel]}
              onPress={onCancel}
              disabled={isSubmitting}
            >
              <Text style={styles.buttonCancelText}>Cancel</Text>
            </TouchableOpacity>
          )}

          {currentStep < 4 ? (
            <TouchableOpacity
              style={[styles.button, styles.buttonPrimary]}
              onPress={handleNext}
              disabled={isSubmitting}
            >
              <Text style={styles.buttonPrimaryText}>Next</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              style={[styles.button, styles.buttonPrimary, isSubmitting && styles.buttonDisabled]}
              onPress={handleSubmit}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <ActivityIndicator color="#ffffff" size="small" />
              ) : (
                <Text style={styles.buttonPrimaryText}>Submit Report</Text>
              )}
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

// Step 1: Temperature and SpO2
function Step1({ formData, setFormData }: { formData: FormData; setFormData: (data: FormData) => void }) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.stepTitle}>Vital Signs</Text>
      <Text style={styles.stepDescription}>Enter your temperature and oxygen saturation if available.</Text>

      {/* Temperature */}
      <View style={styles.fieldContainer}>
        <View style={styles.fieldHeader}>
          <Text style={styles.fieldLabel}>Temperature</Text>
          <TouchableOpacity
            style={styles.toggleButton}
            onPress={() => setFormData({ ...formData, fever_measured: !formData.fever_measured })}
          >
            <Text style={styles.toggleText}>
              {formData.fever_measured ? 'Measured' : 'Not Measured'}
            </Text>
          </TouchableOpacity>
        </View>
        {formData.fever_measured && (
          <>
            <Slider
              style={styles.slider}
              minimumValue={35.0}
              maximumValue={42.0}
              step={0.1}
              value={formData.fever_celsius || 37.0}
              onValueChange={(value) => setFormData({ ...formData, fever_celsius: value })}
              minimumTrackTintColor="#ef4444"
              maximumTrackTintColor="#e5e7eb"
            />
            <Text style={styles.sliderValue}>{formData.fever_celsius?.toFixed(1)}°C</Text>
          </>
        )}
      </View>

      {/* SpO2 */}
      <View style={styles.fieldContainer}>
        <View style={styles.fieldHeader}>
          <Text style={styles.fieldLabel}>Blood Oxygen (SpO2)</Text>
          <TouchableOpacity
            style={styles.toggleButton}
            onPress={() => setFormData({ ...formData, spo2_measured: !formData.spo2_measured })}
          >
            <Text style={styles.toggleText}>
              {formData.spo2_measured ? 'Measured' : 'Not Measured'}
            </Text>
          </TouchableOpacity>
        </View>
        {formData.spo2_measured && (
          <View style={styles.numericInputContainer}>
            <TextInput
              style={styles.numericInput}
              value={formData.spo2_pct?.toString() || ''}
              onChangeText={(text) => {
                const value = parseInt(text) || null;
                if (value === null || (value >= 85 && value <= 100)) {
                  setFormData({ ...formData, spo2_pct: value });
                }
              }}
              keyboardType="numeric"
              maxLength={3}
              placeholder="95"
            />
            <Text style={styles.inputUnit}>%</Text>
          </View>
        )}
      </View>
    </View>
  );
}

// Step 2: Respiratory Symptoms
function Step2({ formData, setFormData }: { formData: FormData; setFormData: (data: FormData) => void }) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.stepTitle}>Respiratory Symptoms</Text>
      <Text style={styles.stepDescription}>Tell us about your respiratory symptoms.</Text>

      {/* Cough Severity */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Cough Severity</Text>
        <SegmentSelector
          values={['None', 'Mild', 'Moderate', 'Severe']}
          selectedIndex={formData.cough_severity}
          onSelect={(index) =>
            setFormData({ ...formData, cough_severity: index as 0 | 1 | 2 | 3 })
          }
        />
      </View>

      {/* Shortness of Breath */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Shortness of Breath</Text>
        <View style={styles.switchContainer}>
          <TouchableOpacity
            style={[styles.switchOption, !formData.dyspnoea && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, dyspnoea: false })}
          >
            <Text style={[styles.switchOptionText, !formData.dyspnoea && styles.switchOptionTextActive]}>
              No
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.switchOption, formData.dyspnoea && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, dyspnoea: true })}
          >
            <Text style={[styles.switchOptionText, formData.dyspnoea && styles.switchOptionTextActive]}>
              Yes
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Fatigue Severity */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Fatigue Level</Text>
        <SegmentSelector
          values={['None', 'Mild', 'Moderate', 'Severe']}
          selectedIndex={formData.fatigue_severity}
          onSelect={(index) =>
            setFormData({ ...formData, fatigue_severity: index as 0 | 1 | 2 | 3 })
          }
        />
      </View>
    </View>
  );
}

// Step 3: Other Symptoms
function Step3({ formData, setFormData }: { formData: FormData; setFormData: (data: FormData) => void }) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.stepTitle}>Other Symptoms</Text>
      <Text style={styles.stepDescription}>Let us know about any other symptoms you're experiencing.</Text>

      {/* Heart Rate */}
      <View style={styles.fieldContainer}>
        <View style={styles.fieldHeader}>
          <Text style={styles.fieldLabel}>Heart Rate</Text>
          <TouchableOpacity
            style={styles.toggleButton}
            onPress={() => setFormData({ ...formData, heart_rate_measured: !formData.heart_rate_measured })}
          >
            <Text style={styles.toggleText}>
              {formData.heart_rate_measured ? 'Measured' : 'Not Measured'}
            </Text>
          </TouchableOpacity>
        </View>
        {formData.heart_rate_measured && (
          <View style={styles.numericInputContainer}>
            <TextInput
              style={styles.numericInput}
              value={formData.heart_rate_bpm?.toString() || ''}
              onChangeText={(text) => {
                const value = parseInt(text) || null;
                if (value === null || (value >= 40 && value <= 200)) {
                  setFormData({ ...formData, heart_rate_bpm: value });
                }
              }}
              keyboardType="numeric"
              maxLength={3}
              placeholder="72"
            />
            <Text style={styles.inputUnit}>bpm</Text>
          </View>
        )}
      </View>

      {/* Sore Throat */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Sore Throat</Text>
        <View style={styles.switchContainer}>
          <TouchableOpacity
            style={[styles.switchOption, !formData.sore_throat && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, sore_throat: false })}
          >
            <Text style={[styles.switchOptionText, !formData.sore_throat && styles.switchOptionTextActive]}>
              No
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.switchOption, formData.sore_throat && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, sore_throat: true })}
          >
            <Text style={[styles.switchOptionText, formData.sore_throat && styles.switchOptionTextActive]}>
              Yes
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Diarrhea */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Diarrhea</Text>
        <View style={styles.switchContainer}>
          <TouchableOpacity
            style={[styles.switchOption, !formData.diarrhoea && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, diarrhoea: false })}
          >
            <Text style={[styles.switchOptionText, !formData.diarrhoea && styles.switchOptionTextActive]}>
              No
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.switchOption, formData.diarrhoea && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, diarrhoea: true })}
          >
            <Text style={[styles.switchOptionText, formData.diarrhoea && styles.switchOptionTextActive]}>
              Yes
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Loss of Smell */}
      <View style={styles.fieldContainer}>
        <Text style={styles.fieldLabel}>Loss of Smell (Anosmia)</Text>
        <View style={styles.switchContainer}>
          <TouchableOpacity
            style={[styles.switchOption, !formData.anosmia && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, anosmia: false })}
          >
            <Text style={[styles.switchOptionText, !formData.anosmia && styles.switchOptionTextActive]}>
              No
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.switchOption, formData.anosmia && styles.switchOptionActive]}
            onPress={() => setFormData({ ...formData, anosmia: true })}
          >
            <Text style={[styles.switchOptionText, formData.anosmia && styles.switchOptionTextActive]}>
              Yes
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

// Step 4: Review
function Step4({ formData, wearableData }: { formData: FormData; wearableData?: any }) {
  const getSymptomText = (severity: number) => {
    const labels = ['None', 'Mild', 'Moderate', 'Severe'];
    return labels[severity];
  };

  return (
    <View style={styles.stepContainer}>
      <Text style={styles.stepTitle}>Review Your Symptoms</Text>
      <Text style={styles.stepDescription}>Please review your symptom report before submitting.</Text>

      <View style={styles.reviewContainer}>
        {/* Vital Signs */}
        <View style={styles.reviewSection}>
          <Text style={styles.reviewSectionTitle}>Vital Signs</Text>
          {formData.fever_measured && (
            <Text style={styles.reviewItem}>Temperature: {formData.fever_celsius?.toFixed(1)}°C</Text>
          )}
          {formData.spo2_measured && (
            <Text style={styles.reviewItem}>SpO2: {formData.spo2_pct}%</Text>
          )}
          {formData.heart_rate_measured && (
            <Text style={styles.reviewItem}>Heart Rate: {formData.heart_rate_bpm} bpm</Text>
          )}
        </View>

        {/* Respiratory */}
        <View style={styles.reviewSection}>
          <Text style={styles.reviewSectionTitle}>Respiratory</Text>
          <Text style={styles.reviewItem}>Cough: {getSymptomText(formData.cough_severity)}</Text>
          <Text style={styles.reviewItem}>Shortness of Breath: {formData.dyspnoea ? 'Yes' : 'No'}</Text>
          <Text style={styles.reviewItem}>Fatigue: {getSymptomText(formData.fatigue_severity)}</Text>
        </View>

        {/* Other Symptoms */}
        <View style={styles.reviewSection}>
          <Text style={styles.reviewSectionTitle}>Other Symptoms</Text>
          <Text style={styles.reviewItem}>Sore Throat: {formData.sore_throat ? 'Yes' : 'No'}</Text>
          <Text style={styles.reviewItem}>Diarrhea: {formData.diarrhoea ? 'Yes' : 'No'}</Text>
          <Text style={styles.reviewItem}>Loss of Smell: {formData.anosmia ? 'Yes' : 'No'}</Text>
        </View>

        {/* Wearable Data */}
        {wearableData && (
          <View style={styles.reviewSection}>
            <Text style={styles.reviewSectionTitle}>Wearable Data</Text>
            {wearableData.hrv_rmssd_ms && (
              <Text style={styles.reviewItem}>HRV: {wearableData.hrv_rmssd_ms} ms</Text>
            )}
            {wearableData.resting_hr_bpm && (
              <Text style={styles.reviewItem}>Resting HR: {wearableData.resting_hr_bpm} bpm</Text>
            )}
            {wearableData.sleep_hours && (
              <Text style={styles.reviewItem}>Sleep: {wearableData.sleep_hours} hours</Text>
            )}
            {wearableData.step_count && (
              <Text style={styles.reviewItem}>Steps: {wearableData.step_count.toLocaleString()}</Text>
            )}
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  progressContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingVertical: 20,
    backgroundColor: '#f9fafb',
  },
  progressStep: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  progressDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#e5e7eb',
    alignItems: 'center',
    justifyContent: 'center',
  },
  progressDotActive: {
    backgroundColor: '#3b82f6',
  },
  progressDotText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#9ca3af',
  },
  progressDotTextActive: {
    color: '#ffffff',
  },
  progressLine: {
    width: 40,
    height: 2,
    backgroundColor: '#e5e7eb',
    marginHorizontal: 8,
  },
  progressLineActive: {
    backgroundColor: '#3b82f6',
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
  },
  stepContainer: {
    paddingVertical: 24,
  },
  stepTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  stepDescription: {
    fontSize: 16,
    color: '#6b7280',
    marginBottom: 32,
    lineHeight: 24,
  },
  fieldContainer: {
    marginBottom: 32,
  },
  fieldHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  fieldLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#374151',
  },
  toggleButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#f3f4f6',
    borderRadius: 16,
  },
  toggleText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#6b7280',
  },
  slider: {
    width: '100%',
    height: 40,
  },
  sliderThumb: {
    width: 24,
    height: 24,
    backgroundColor: '#3b82f6',
  },
  sliderValue: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    textAlign: 'center',
    marginTop: 8,
  },
  numericInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 4,
  },
  numericInput: {
    flex: 1,
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
  },
  inputUnit: {
    fontSize: 16,
    color: '#6b7280',
    marginLeft: 8,
  },
  segmentRow: {
    flexDirection: 'row',
    backgroundColor: '#f3f4f6',
    borderRadius: 10,
    padding: 2,
  },
  segmentOption: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 8,
  },
  segmentOptionActive: {
    backgroundColor: '#3b82f6',
  },
  segmentText: {
    fontSize: 13,
    fontWeight: '500',
    color: '#6b7280',
  },
  segmentTextActive: {
    color: '#ffffff',
  },
  switchContainer: {
    flexDirection: 'row',
    backgroundColor: '#f3f4f6',
    borderRadius: 12,
    padding: 4,
  },
  switchOption: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 8,
  },
  switchOptionActive: {
    backgroundColor: '#ffffff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  switchOptionText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#6b7280',
  },
  switchOptionTextActive: {
    color: '#1f2937',
  },
  reviewContainer: {
    backgroundColor: '#f9fafb',
    borderRadius: 12,
    padding: 20,
  },
  reviewSection: {
    marginBottom: 20,
  },
  reviewSectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 8,
  },
  reviewItem: {
    fontSize: 14,
    color: '#4b5563',
    marginBottom: 4,
    paddingLeft: 16,
  },
  footer: {
    paddingHorizontal: 24,
    paddingVertical: 16,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  buttonRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  spacer: {
    flex: 1,
  },
  button: {
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 100,
  },
  buttonPrimary: {
    backgroundColor: '#3b82f6',
  },
  buttonSecondary: {
    backgroundColor: '#f3f4f6',
  },
  buttonCancel: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#d1d5db',
  },
  buttonDisabled: {
    backgroundColor: '#9ca3af',
  },
  buttonPrimaryText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  buttonSecondaryText: {
    color: '#374151',
    fontSize: 16,
    fontWeight: '600',
  },
  buttonCancelText: {
    color: '#6b7280',
    fontSize: 16,
    fontWeight: '600',
  },
});
