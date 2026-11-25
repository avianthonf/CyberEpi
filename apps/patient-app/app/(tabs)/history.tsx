import React, {useState} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import {Ionicons} from '@expo/vector-icons';
import {useRiskScoreHistory, type RiskHistoryItem} from '@/hooks/useRiskScore';
import {getRiskTierColor} from '@/store/riskStore';
import {Svg, Line, Path, Circle} from 'react-native-svg';

export default function HistoryScreen() {
  const [selectedPeriod, setSelectedPeriod] = useState<'7' | '30' | '90'>('7');
  const {
    data: historyData,
    isLoading,
    error,
    refetch,
  } = useRiskScoreHistory(30); // Backend hardcoded limit 30, ignores days param

  // Client-side filtering: backend returns last 30, filter by selected period
  const allHistory: RiskHistoryItem[] = Array.isArray(historyData) ? historyData : [];
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - parseInt(selectedPeriod));
  
  const history = allHistory
    .filter(item => {
      const itemDate = new Date(item.time);
      return itemDate >= cutoffDate;
    })
    .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()); // Chronological order

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
      (item): item is RiskHistoryItem & {risk_score: number} =>
        item.risk_score !== null && item.risk_score !== undefined,
    );
    if (chartItems.length === 0) return null;

    const width = 320;
    const height = 200;
    const padding = 20;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Generate points for the line chart
    const points = chartItems.map((item, index) => {
      // Handle single point case: center it horizontally
      const x =
        chartItems.length === 1
          ? padding + chartWidth / 2
          : padding + (index / (chartItems.length - 1)) * chartWidth;
      const y = padding + chartHeight - item.risk_score * chartHeight;
      return {x, y, score: item.risk_score, tier: item.risk_tier};
    });

    // Create path for the line (only if multiple points)
    const pathData =
      chartItems.length > 1
        ? points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
            .join(' ')
        : '';

    return (
      <View style={styles.chartContainer}>
        <Svg width={width} height={height}>
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map(value => {
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

          {/* Risk score line (only for multiple points) */}
          {pathData && <Path d={pathData} stroke="#3b82f6" strokeWidth="2" fill="none" />}

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
      }>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>History</Text>
        <Text style={styles.subtitle}>
          Track your symptom reports and risk scores over time
        </Text>
      </View>

      {/* Period Selector */}
      <View style={styles.periodSelector}>
        {(['7', '30', '90'] as const).map(period => (
          <TouchableOpacity
            key={period}
            style={[
              styles.periodButton,
              selectedPeriod === period && styles.periodButtonActive,
            ]}
            onPress={() => setSelectedPeriod(period)}>
            <Text
              style={[
                styles.periodButtonText,
                selectedPeriod === period && styles.periodButtonTextActive,
              ]}>
              {period === '7'
                ? '7 Days'
                : period === '30'
                  ? '30 Days'
                  : '90 Days'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Backend limit info */}
      <View style={styles.periodInfo}>
        <Ionicons name="information-circle-outline" size={16} color="#6b7280" />
        <Text style={styles.periodInfoText}>
          Up to 30 recent reports, filtered by selected period
        </Text>
      </View>

      {/* Risk Score Chart */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Risk Score Trend</Text>
        {error ? (
          <View style={styles.errorState}>
            <Ionicons name="alert-circle-outline" size={48} color="#ef4444" />
            <Text style={styles.errorTitle}>Failed to Load History</Text>
            <Text style={styles.errorDescription}>
              Unable to fetch your history. Check your connection and try again.
            </Text>
            <TouchableOpacity style={styles.retryButton} onPress={() => refetch()}>
              <Ionicons name="refresh-outline" size={20} color="#ffffff" />
              <Text style={styles.retryButtonText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : isLoading && allHistory.length === 0 ? (
          <View style={styles.emptyChart}>
            <Text style={styles.emptyText}>Loading...</Text>
          </View>
        ) : history.length > 0 ? (
          renderChart()
        ) : (
          <View style={styles.emptyChart}>
            <Text style={styles.emptyText}>
              {allHistory.length === 0 
                ? 'No risk score data available. Start tracking symptoms to see your trend.'
                : 'No data in selected period. Try a longer time range.'}
            </Text>
          </View>
        )}
      </View>

      {/* History List */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Symptom Reports</Text>
        {error ? (
          <View style={styles.errorState}>
            <Ionicons name="alert-circle-outline" size={48} color="#ef4444" />
            <Text style={styles.errorTitle}>Connection Error</Text>
            <TouchableOpacity style={styles.retryButton} onPress={() => refetch()}>
              <Ionicons name="refresh-outline" size={20} color="#ffffff" />
              <Text style={styles.retryButtonText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : isLoading && allHistory.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="hourglass-outline" size={48} color="#9ca3af" />
            <Text style={styles.emptyTitle}>Loading History</Text>
          </View>
        ) : history.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="document-outline" size={48} color="#9ca3af" />
            <Text style={styles.emptyTitle}>
              {allHistory.length === 0 ? 'No History' : 'No Reports in This Period'}
            </Text>
            <Text style={styles.emptyDescription}>
              {allHistory.length === 0 
                ? 'Your symptom reports will appear here once you start tracking'
                : `No reports in last ${selectedPeriod} days. Try selecting a longer period.`}
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
                    {backgroundColor: getRiskTierColor(item.risk_tier)},
                  ]}>
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
                      <Ionicons
                        name="chevron-forward"
                        size={12}
                        color="#6b7280"
                      />
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
  periodInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 24,
    gap: 8,
  },
  periodInfoText: {
    fontSize: 14,
    color: '#1e40af',
    flex: 1,
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
  errorState: {
    borderRadius: 12,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#fecaca',
    backgroundColor: '#fef2f2',
  },
  errorTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#991b1b',
    marginTop: 16,
    marginBottom: 8,
  },
  errorDescription: {
    fontSize: 14,
    color: '#dc2626',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 16,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ef4444',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  retryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
  },
});
