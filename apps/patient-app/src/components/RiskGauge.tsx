import React, {useEffect, useRef} from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  Animated,
  TouchableOpacity,
  Alert,
} from 'react-native';
import Svg, {Path, Circle, Defs, LinearGradient, Stop} from 'react-native-svg';
import {RiskTier} from '@/types';
import {
  getRiskTierColor,
  getRiskTierLabel,
  getRiskTierFromScore,
} from '@/store/riskStore';

interface RiskGaugeProps {
  score: number | null;
  tier: RiskTier | null;
  size?: number;
  showLabel?: boolean;
  animated?: boolean;
  onCallPress?: () => void;
  testID?: string;
}

const {width: screenWidth} = Dimensions.get('window');
const GAUGE_SIZE = Math.min(screenWidth * 0.8, 280);

export function RiskGauge({
  score,
  tier,
  size = GAUGE_SIZE,
  showLabel = true,
  animated = true,
  onCallPress,
  testID,
}: RiskGaugeProps) {
  const animatedValue = useRef(new Animated.Value(0)).current;
  const scaleValue = useRef(new Animated.Value(1)).current;

  // Animation configuration
  useEffect(() => {
    let springAnimation: Animated.CompositeAnimation | null = null;
    let pulseAnimation: Animated.CompositeAnimation | null = null;

    if (score !== null && animated) {
      springAnimation = Animated.spring(animatedValue, {
        toValue: score,
        tension: 100,
        friction: 8,
        useNativeDriver: false,
      });
      springAnimation.start();

      if (tier === 'urgent') {
        pulseAnimation = Animated.loop(
          Animated.sequence([
            Animated.timing(scaleValue, {
              toValue: 1.05,
              duration: 600,
              useNativeDriver: true,
            }),
            Animated.timing(scaleValue, {
              toValue: 1,
              duration: 600,
              useNativeDriver: true,
            }),
          ]),
        );
        pulseAnimation.start();
      }
    } else if (score !== null && !animated) {
      animatedValue.setValue(score);
    }

    return () => {
      springAnimation?.stop();
      pulseAnimation?.stop();
    };
  }, [score, tier, animated, animatedValue, scaleValue]);

  // Calculate gauge path
  const createGaugePath = (progress: number) => {
    const radius = size * 0.35;
    const centerX = size / 2;
    const centerY = size * 0.6;
    const startAngle = Math.PI;
    const endAngle = startAngle + progress * Math.PI;

    const x1 = centerX + radius * Math.cos(startAngle);
    const y1 = centerY + radius * Math.sin(startAngle);
    const x2 = centerX + radius * Math.cos(endAngle);
    const y2 = centerY + radius * Math.sin(endAngle);

    const largeArcFlag = progress > 0.5 ? 1 : 0;

    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2}`;
  };

  // Color from score value — reuse the store's tier mapping (single source of truth)
  const getScoreColor = (value: number): string =>
    getRiskTierColor(getRiskTierFromScore(value));

  const handleCallPress = () => {
    if (tier === 'urgent' && onCallPress) {
      Alert.alert(
        'Emergency Call',
        'This research score is not validated medical advice. If you are experiencing a medical emergency, contact your local emergency services. Do not place emergency calls while testing synthetic data.',
        [
          {text: 'Cancel', style: 'cancel'},
          {text: 'Call Now', onPress: onCallPress},
        ],
        {cancelable: false},
      );
    }
  };

  if (score === null) {
    return (
      <View style={[styles.container, {width: size, height: size}]}>
        <View style={[styles.gaugeContainer, {width: size, height: size}]}>
          <Svg width={size} height={size}>
            {/* Background arc */}
            <Path
              d={createGaugePath(1)}
              stroke="#e5e7eb"
              strokeWidth={size * 0.08}
              fill="none"
              strokeLinecap="round"
            />
          </Svg>
          <View style={styles.centerContent}>
            <Text style={styles.noDataText}>No Data</Text>
            <Text style={styles.noDataSubtext}>
              Submit at least 3 reports to see your risk score
            </Text>
          </View>
        </View>
      </View>
    );
  }

  return (
    <View
      testID={testID}
      style={[styles.container, {width: size, height: size}]}>
      <Animated.View
        style={[
          styles.gaugeContainer,
          {width: size, height: size},
          {transform: [{scale: scaleValue}]},
        ]}>
        <Svg width={size} height={size}>
          <Defs>
            <LinearGradient
              id="gaugeGradient"
              x1="0%"
              y1="0%"
              x2="100%"
              y2="0%">
              <Stop offset="0%" stopColor={getScoreColor(0)} />
              <Stop offset="33%" stopColor={getScoreColor(0.33)} />
              <Stop offset="66%" stopColor={getScoreColor(0.66)} />
              <Stop offset="100%" stopColor={getScoreColor(1)} />
            </LinearGradient>
          </Defs>

          {/* Background arc */}
          <Path
            d={createGaugePath(1)}
            stroke="#e5e7eb"
            strokeWidth={size * 0.08}
            fill="none"
            strokeLinecap="round"
          />

          {/* Progress arc */}
          <Path
            d={createGaugePath(Math.min(Math.max(score ?? 0, 0), 1))}
            stroke="url(#gaugeGradient)"
            strokeWidth={size * 0.08}
            fill="none"
            strokeLinecap="round"
          />

          {/* Risk tier indicators at backend thresholds: 0.3, 0.6, 0.8 */}
          {[0.3, 0.6, 0.8].map((threshold, index) => {
            const radius = size * 0.35;
            const centerX = size / 2;
            const centerY = size * 0.6;
            const angle = Math.PI + threshold * Math.PI;
            const x = centerX + radius * Math.cos(angle);
            const y = centerY + radius * Math.sin(angle);

            return (
              <Circle
                key={index}
                cx={x}
                cy={y}
                r={size * 0.02}
                fill={score > threshold ? getScoreColor(score) : '#9ca3af'}
              />
            );
          })}
        </Svg>

        {/* Center content */}
        <View style={styles.centerContent}>
          <Animated.Text
            style={[
              styles.scoreText,
              {
                color: getScoreColor(score),
              },
            ]}>
            {Math.round(score * 100)}%
          </Animated.Text>

          {showLabel && (
            <Text
              style={[
                styles.tierText,
                {
                  color: getRiskTierColor(tier),
                },
              ]}>
              {getRiskTierLabel(tier)}
            </Text>
          )}

          {tier === 'urgent' && (
            <TouchableOpacity
              style={[
                styles.callButton,
                {backgroundColor: getScoreColor(score)},
              ]}
              onPress={handleCallPress}
              activeOpacity={0.8}>
              <Text style={styles.callButtonText}>CALL NOW</Text>
            </TouchableOpacity>
          )}
        </View>
      </Animated.View>

      {/* Risk tier labels */}
      {showLabel && (
        <View style={[styles.labelsContainer, {width: size * 0.8}]}>
          <View style={styles.labelItem}>
            <View style={[styles.labelDot, {backgroundColor: '#10b981'}]} />
            <Text style={styles.labelText}>Low</Text>
          </View>
          <View style={styles.labelItem}>
            <View style={[styles.labelDot, {backgroundColor: '#f59e0b'}]} />
            <Text style={styles.labelText}>Moderate</Text>
          </View>
          <View style={styles.labelItem}>
            <View style={[styles.labelDot, {backgroundColor: '#f97316'}]} />
            <Text style={styles.labelText}>Consult</Text>
          </View>
          <View style={styles.labelItem}>
            <View style={[styles.labelDot, {backgroundColor: '#ef4444'}]} />
            <Text style={styles.labelText}>Urgent</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  gaugeContainer: {
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
  },
  centerContent: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
    top: '45%',
  },
  scoreText: {
    fontSize: 48,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  tierText: {
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
    marginTop: 4,
  },
  noDataText: {
    fontSize: 24,
    fontWeight: '600',
    color: '#6b7280',
    textAlign: 'center',
  },
  noDataSubtext: {
    fontSize: 12,
    color: '#9ca3af',
    textAlign: 'center',
    marginTop: 8,
    maxWidth: 200,
  },
  callButton: {
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 3,
  },
  callButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  labelsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 20,
    paddingHorizontal: 10,
  },
  labelItem: {
    alignItems: 'center',
  },
  labelDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginBottom: 4,
  },
  labelText: {
    fontSize: 10,
    color: '#6b7280',
    fontWeight: '500',
  },
});
