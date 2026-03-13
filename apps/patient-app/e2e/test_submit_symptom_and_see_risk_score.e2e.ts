import { by, device, element, expect } from 'detox';

describe('Submit Symptom and See Risk Score E2E', () => {
  beforeAll(async () => {
    await device.launchApp({ newInstance: true });
  });

  beforeEach(async () => {
    await device.reloadReactNative();
  });

  it('should login with test user', async () => {
    // Wait for login screen
    await expect(element(by.text('Sign In with Keycloak'))).toBeVisible();

    // Tap login button
    await element(by.text('Sign In with Keycloak')).tap();

    // After OAuth redirect completes, we should see the home screen
    await waitFor(element(by.text('Your Risk Score')))
      .toBeVisible()
      .withTimeout(10000);
  });

  it('should navigate to symptoms tab and start a report', async () => {
    // Navigate to symptoms tab
    await element(by.text('Symptoms')).tap();

    // Verify symptoms screen
    await expect(element(by.text('Symptom Tracking'))).toBeVisible();

    // Tap "Report New Symptoms"
    await element(by.text('Report New Symptoms')).tap();

    // Should see Step 1: Vital Signs
    await expect(element(by.text('Vital Signs'))).toBeVisible();
  });

  it('should fill in Step 1 — temperature and SpO2', async () => {
    // Toggle temperature measurement on
    await element(by.text('Not Measured')).atIndex(0).tap();

    // The slider should now be visible; set a value
    // Note: Detox slider interaction is limited, we verify it's visible
    await expect(element(by.text('°C'))).toBeVisible();

    // Toggle SpO2 measurement on
    await element(by.text('Not Measured')).atIndex(0).tap();

    // Enter SpO2 value
    await element(by.type('RCTUITextField')).atIndex(0).typeText('97');

    // Tap Next
    await element(by.text('Next')).tap();
  });

  it('should fill in Step 2 — respiratory symptoms', async () => {
    // Verify Step 2
    await expect(element(by.text('Respiratory Symptoms'))).toBeVisible();

    // Select "Mild" cough
    await element(by.text('Mild')).atIndex(0).tap();

    // Toggle shortness of breath to Yes
    await element(by.text('Yes')).atIndex(0).tap();

    // Select "Moderate" fatigue
    await element(by.text('Moderate')).atIndex(1).tap();

    // Tap Next
    await element(by.text('Next')).tap();
  });

  it('should fill in Step 3 — other symptoms', async () => {
    // Verify Step 3
    await expect(element(by.text('Other Symptoms'))).toBeVisible();

    // Toggle sore throat to Yes
    await element(by.text('Yes')).atIndex(0).tap();

    // Tap Next
    await element(by.text('Next')).tap();
  });

  it('should review and submit the symptom report', async () => {
    // Verify Step 4 — Review
    await expect(element(by.text('Review Your Symptoms'))).toBeVisible();

    // Verify summary data visible
    await expect(element(by.text('Vital Signs'))).toBeVisible();
    await expect(element(by.text('Respiratory'))).toBeVisible();
    await expect(element(by.text('Other Symptoms'))).toBeVisible();

    // Submit report
    await element(by.text('Submit Report')).tap();

    // Wait for submission to complete
    await waitFor(element(by.text('Success')))
      .toBeVisible()
      .withTimeout(15000);

    // Navigate to home
    await element(by.text('OK')).tap();
  });

  it('should display the risk gauge on the home screen', async () => {
    // Navigate to home
    await element(by.text('Home')).tap();

    // Verify risk gauge section is visible
    await waitFor(element(by.text('Your Risk Score')))
      .toBeVisible()
      .withTimeout(10000);

    // If sufficient reports exist, the gauge percentage should be visible
    // Otherwise, the "Insufficient data" message should show
    try {
      await expect(element(by.text('%'))).toBeVisible();
    } catch {
      await expect(
        element(by.text('Insufficient data: Need at least 3 symptom reports'))
      ).toBeVisible();
    }
  });
});
