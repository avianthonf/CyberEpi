import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { RiskGauge } from '@/components/RiskGauge';

describe('RiskGauge Component', () => {
  it('renders green for low risk score', () => {
    const { getByText } = render(
      <RiskGauge score={0.1} tier="low" />
    );
    
    expect(getByText('10%')).toBeTruthy();
    expect(getByText('Low Risk')).toBeTruthy();
  });

  it('renders orange for moderate risk score', () => {
    const { getByText } = render(
      <RiskGauge score={0.3} tier="moderate" />
    );
    
    expect(getByText('30%')).toBeTruthy();
    expect(getByText('Moderate Risk')).toBeTruthy();
  });

  it('renders orange for consult risk score', () => {
    const { getByText } = render(
      <RiskGauge score={0.6} tier="consult" />
    );
    
    expect(getByText('60%')).toBeTruthy();
    expect(getByText('Consult Physician')).toBeTruthy();
  });

  it('renders red with urgent banner for urgent risk score', () => {
    const mockOnCallPress = jest.fn();
    const { getByText } = render(
      <RiskGauge 
        score={0.8} 
        tier="urgent" 
        onCallPress={mockOnCallPress}
      />
    );
    
    expect(getByText('80%')).toBeTruthy();
    expect(getByText('Urgent - Call Now')).toBeTruthy();
    expect(getByText('CALL NOW')).toBeTruthy();
  });

  it('shows "No Data" when score is null', () => {
    const { getByText } = render(
      <RiskGauge score={null} tier={null} />
    );
    
    expect(getByText('No Data')).toBeTruthy();
    expect(getByText('Submit at least 3 reports to see your risk score')).toBeTruthy();
  });

  it('calls onCallPress when call button is pressed', () => {
    const mockOnCallPress = jest.fn();
    const { getByText } = render(
      <RiskGauge 
        score={0.9} 
        tier="urgent" 
        onCallPress={mockOnCallPress}
      />
    );
    
    fireEvent.press(getByText('CALL NOW'));
    expect(mockOnCallPress).toHaveBeenCalled();
  });

  it('does not show call button for non-urgent tiers', () => {
    const mockOnCallPress = jest.fn();
    const { queryByText } = render(
      <RiskGauge 
        score={0.3} 
        tier="moderate" 
        onCallPress={mockOnCallPress}
      />
    );
    
    expect(queryByText('CALL NOW')).toBeFalsy();
  });

  it('can hide label when showLabel is false', () => {
    const { queryByText } = render(
      <RiskGauge 
        score={0.5} 
        tier="moderate" 
        showLabel={false}
      />
    );
    
    expect(queryByText('Moderate Risk')).toBeFalsy();
  });

  it('can disable animation when animated is false', () => {
    const { getByText } = render(
      <RiskGauge 
        score={0.7} 
        tier="consult" 
        animated={false}
      />
    );
    
    expect(getByText('70%')).toBeTruthy();
  });

  it('renders with custom size', () => {
    const customSize = 200;
    const { getByTestId } = render(
      <RiskGauge 
        score={0.4} 
        tier="moderate" 
        size={customSize}
        testID="risk-gauge"
      />
    );
    
    const gauge = getByTestId('risk-gauge');
    expect(gauge).toBeTruthy();
  });
});
