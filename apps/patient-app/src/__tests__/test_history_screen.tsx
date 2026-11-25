import React from 'react';
import {fireEvent, render} from '@testing-library/react-native';
import {Circle} from 'react-native-svg';
import HistoryScreen from '../../app/(tabs)/history';
import {useRiskScoreHistory} from '@/hooks/useRiskScore';
import {getRiskTierFromScore} from '@/store/riskStore';

jest.mock('@/hooks/useRiskScore', () => ({
  useRiskScoreHistory: jest.fn(),
}));

const currentTime = Date.parse('2026-10-19T12:00:00Z');
const millisecondsPerDay = 24 * 60 * 60 * 1000;

function report(daysAgo: number, score: number | null, marker: string) {
  return {
    time: new Date(currentTime - daysAgo * millisecondsPerDay).toISOString(),
    risk_score: score,
    risk_tier: score === null ? null : getRiskTierFromScore(score),
    symptoms: {[marker]: true},
  };
}

const historyHook = useRiskScoreHistory as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers({now: currentTime});
});

afterEach(() => {
  jest.useRealTimers();
});

it('keeps the first scored report visible with finite chart coordinates', () => {
  historyHook.mockReturnValue({
    data: [report(1, 0.6, 'first')],
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  });

  const view = render(<HistoryScreen />);
  const points = view.UNSAFE_getAllByType(Circle);
  expect(points).toHaveLength(1);
  expect(Number.isFinite(points[0].props.cx)).toBe(true);
  expect(Number.isFinite(points[0].props.cy)).toBe(true);
  expect(view.getByText('first: true')).toBeTruthy();
});

it('plots reports chronologically even when the API returns newest first', () => {
  historyHook.mockReturnValue({
    data: [report(1, 0.9, 'newest'), report(3, 0.2, 'oldest'), report(2, 0.6, 'middle')],
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  });

  const view = render(<HistoryScreen />);
  const points = view.UNSAFE_getAllByType(Circle);
  expect(points).toHaveLength(3);
  expect(points[0].props.cx).toBeLessThan(points[1].props.cx);
  expect(points[1].props.cx).toBeLessThan(points[2].props.cx);
  expect(points[0].props.cy).toBeGreaterThan(points[1].props.cy);
  expect(points[1].props.cy).toBeGreaterThan(points[2].props.cy);
});

it('filters returned reports by the selected period, including its cutoff', () => {
  historyHook.mockReturnValue({
    data: [report(1, 0.4, 'recent'), report(7, 0.5, 'cutoff'), report(15, 0.6, 'older'), report(45, 0.7, 'oldest')],
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  });

  const view = render(<HistoryScreen />);
  expect(view.getByText('recent: true')).toBeTruthy();
  expect(view.getByText('cutoff: true')).toBeTruthy();
  expect(view.queryByText('older: true')).toBeNull();
  expect(view.queryByText('oldest: true')).toBeNull();

  fireEvent.press(view.getByText('30 Days'));
  expect(view.getByText('older: true')).toBeTruthy();
  expect(view.queryByText('oldest: true')).toBeNull();

  fireEvent.press(view.getByText('90 Days'));
  expect(view.getByText('oldest: true')).toBeTruthy();
});

it('does not present a failed history request as an empty patient history', () => {
  const refetch = jest.fn();
  historyHook.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error('Service unavailable'),
    refetch,
  });

  const view = render(<HistoryScreen />);
  expect(view.queryByText('No History')).toBeNull();
  fireEvent.press(view.getAllByText('Retry')[0]);
  expect(refetch).toHaveBeenCalledTimes(1);

  historyHook.mockReturnValue({
    data: [report(1, 0.6, 'recovered')],
    isLoading: false,
    error: null,
    refetch,
  });
  view.rerender(<HistoryScreen />);
  expect(view.queryByText('Retry')).toBeNull();
  expect(view.getByText('recovered: true')).toBeTruthy();
});

it('shows genuinely empty history without offering an error retry', () => {
  historyHook.mockReturnValue({
    data: [],
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  });

  const view = render(<HistoryScreen />);
  expect(view.getByText('No History')).toBeTruthy();
  expect(view.queryByText('Retry')).toBeNull();
});

it('retains unscored reports without plotting an invented risk value', () => {
  historyHook.mockReturnValue({
    data: [report(1, null, 'unscored')],
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  });

  const view = render(<HistoryScreen />);
  expect(view.getByText('unscored: true')).toBeTruthy();
  expect(view.getByText('Insufficient data')).toBeTruthy();
  expect(view.UNSAFE_queryAllByType(Circle)).toHaveLength(0);
});
