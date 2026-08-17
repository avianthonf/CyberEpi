import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRiskScoreHistory } from '@/hooks/useRiskScore';
import { getRiskTierColor } from '@/store/riskStore';
import { Svg, Line, Path, Circle } from 'react-native-svg';
import { RiskTier } from '@/types';

interface HistoryItem {
  time: string;
  risk_score: number | null;
  risk_tier: RiskTier | null;
  symptoms: Record<string, unknown> | null;
}

export default function HistoryScreen() {
  const [selectedPeriod, setSelectedPeriod] = useState<'7' | '30' | '90'>('7');
  const { data: historyData, isLoading, refetch } = useRiskScoreHistory(parseInt(selectedPeriod));

  const history: HistoryItem[] = Array.isArray(historyData) ? historyData : [];

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const renderChart = () => {
    const chartItems = history.filter(
      (item): item is HistoryItem & { risk_score: number } =>
        item.risk_score !== null && item.risk_score !== undefined
    );
    if (chartItems.length === 0) return null;

    const width = 320;
    const height = 200;
    const padding = 20;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Generate points for the line chart
    const points = chartItems.map((item, index) => {
      const x = padding + (index / (chartItems.length - 1)) * chartWidth;
      const y = padding + chartHeight - item.risk_score * chartHeight;
      return { x, y, score: item.risk_score, tier: item.risk_tier };
    });

    // Create path for the line
    const pathData = points
      .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
      .join(' ');

    return (
      <View style={styles.chartContainer}>
        <Svg width={width} height={height}>
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((value) => {
            const y = padding + chartHeight - value * chartHeight;
            return (
              <Line
                key={value}
                x1={padding}
                y1={y}
                x2={width - padding}
                y2={y}
                stroke="#e5e7eb"
                strokeWidth="1"
              />
            );
          })}

          {/* Risk score line */}
          <Path
            d={pathData}
            stroke="#3b82f6"
            strokeWidth="2"
            fill="none"
          />

          {/* Data points */}
          {points.map((point, index) => (
            <Circle
              key={index}
              cx={point.x}
              cy={point.y}
              r="4"
              fill={getRiskTierColor(point.tier)}
            />
          ))}
        </Svg>

        {/* Y-axis labels */}
        <View style={styles.yAxisLabels}>
          <Text style={styles.axisLabel}>100%</Text>
          <Text style={styles.axisLabel}>75%</Text>
          <Text style={styles.axisLabel}>50%</Text>
          <Text style={styles.axisLabel}>25%</Text>
          <Text style={styles.axisLabel}>0%</Text>
        </View>
      </View>
    );
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isLoading} onRefresh={refetch} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>History</Text>
        <Text style={styles.subtitle}>
          Track your symptom reports and risk scores over time
        </Text>
      </View>

      {/* Period Selector */}
      <View style={styles.periodSelector}>
        {(['7', '30', '90'] as const).map((period) => (
          <TouchableOpacity
            key={period}
            style={[
              styles.periodButton,
              selectedPeriod === period && styles.periodButtonActive,
            ]}
            onPress={() => setSelectedPeriod(period)}
          >
            <Text
              style={[
                styles.periodButtonText,
                selectedPeriod === period && styles.periodButtonTextActive,
              ]}
            >
              {period === '7' ? '7 Days' : period === '30' ? '30 Days' : '90 Days'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Risk Score Chart */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Risk Score Trend</Text>
        {history.length > 0 ? (
          renderChart()
        ) : (
          <View style={styles.emptyChart}>
            <Text style={styles.emptyText}>No data available</Text>
          </View>
        )}
      </View>

      {/* History List */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Symptom Reports</Text>
        {history.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="document-outline" size={48} color="#9ca3af" />
            <Text style={styles.emptyTitle}>No History</Text>
            <Text style={styles.emptyDescription}>
              Your symptom reports will appear here once you start tracking
            </Text>
          </View>
        ) : (
          history.map((item, index) => (
            <View key={index} style={styles.historyItem}>
              <View style={styles.historyHeader}>
                <Text style={styles.historyDate}>{formatDate(item.time)}</Text>
                <View
                  style={[
                    styles.riskBadge,
                    { backgroundColor: getRiskTierColor(item.risk_tier) },
                  ]}
                >
                  <Text style={styles.riskText}>
                    {item.risk_score !== null
                      ? `${Math.round(item.risk_score * 100)}% - ${item.risk_tier}`
                      : 'Insufficient data'}
                  </Text>
                </View>
              </View>
              {item.symptoms && (
                <View style={styles.symptomsContainer}>
                  {Object.entries(item.symptoms).map(([key, value], i) => (
                    <View key={i} style={styles.symptomItem}>
                      <Ionicons name="chevron-forward" size={12} color="#6b7280" />
                      <Text style={styles.symptomText}>
                        {key}: {String(value)}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          ))
        )}
      </View>

      {/* Export Options */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Export Data</Text>
        <View style={styles.exportOptions}>
          <TouchableOpacity style={styles.exportButton}>
            <Ionicons name="download-outline" size={20} color="#3b82f6" />
            <Text style={styles.exportButtonText}>Export as PDF</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.exportButton}>
            <Ionicons name="share-outline" size={20} color="#3b82f6" />
            <Text style={styles.exportButtonText}>Share with Doctor</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  content: {
    padding: 16,
  },
  header: {
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#6b7280',
    lineHeight: 24,
  },
  periodSelector: {
    flexDirection: 'row',
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 4,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  periodButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 8,
  },
  periodButtonActive: {
    backgroundColor: '#3b82f6',
  },
  periodButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#6b7280',
  },
  periodButtonTextActive: {
    color: '#ffffff',
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 16,
  },
  chartContainer: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    position: 'relative',
  },
  emptyChart: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  emptyText: {
    fontSize: 16,
    color: '#6b7280',
  },
  yAxisLabels: {
    position: 'absolute',
    left: 0,
    top: 20,
    bottom: 20,
    justifyContent: 'space-between',
  },
  axisLabel: {
    fontSize: 10,
    color: '#6b7280',
  },
  historyItem: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  historyDate: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
  },
  riskBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  riskText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#ffffff',
  },
  symptomsContainer: {
    gap: 4,
  },
  symptomItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  symptomText: {
    fontSize: 14,
    color: '#4b5563',
  },
  emptyState: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    marginTop: 16,
    marginBottom: 8,
  },
  emptyDescription: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
    lineHeight: 20,
  },
  exportOptions: {
    gap: 12,
  },
  exportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#3b82f6',
    borderRadius: 12,
    padding: 16,
    gap: 12,
  },
  exportButtonText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#3b82f6',
  },
});
