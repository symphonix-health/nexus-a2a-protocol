const { test, expect } = require('@playwright/test');

test.describe('Command Centre dashboard', () => {
  test('loads dashboard shell and core monitoring panels', async ({ page }) => {
    await page.goto('http://127.0.0.1:8099/');

    await expect(page).toHaveTitle(/NEXUS-A2A Command Centre/);
    await expect(page.getByRole('heading', { level: 1, name: /NEXUS-A2A Command Centre/i })).toBeVisible();

    await expect(page.getByRole('heading', { level: 2, name: 'Network Topology' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Agent Metrics Heatmap' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Scenario Flow Board' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Event Timeline' })).toBeVisible();

    await expect(page.locator('#topology-svg')).toBeVisible();
    await expect(page.locator('#heatmap-table')).toBeVisible();
    await expect(page.locator('#flow-lane-queued')).toBeVisible();
    await expect(page.locator('#flow-lane-in-progress')).toBeVisible();
    await expect(page.locator('#flow-lane-blocked')).toBeVisible();
    await expect(page.locator('#flow-lane-completed')).toBeVisible();
    await expect(page.locator('#timeline-container')).toBeVisible();

    const connectionText = page.locator('#connection-text');
    await expect(connectionText).toBeVisible();
    await expect.poll(async () => (await connectionText.textContent())?.trim() || '').not.toBe('');
    await expect(connectionText).toContainText(/Connected|Disconnected|Connecting/i);
  });

  test('renders risk badges and observer controls for blocked journeys', async ({ page }) => {
    await page.goto('http://127.0.0.1:8099/');

    await page.evaluate(() => {
      const payload = {
        agent: 'triage-agent',
        task_id: 'VISIT-OBS-1001-triage',
        event: 'nexus.task.error',
        duration_ms: 65000,
        retry_count: 3,
      };

      window.handleWebSocketMessage({ type: 'task.event', payload });
    });

    const blockedLane = page.locator('#flow-lane-blocked');
    await expect(blockedLane.locator('.flow-card').first()).toBeVisible();
    await expect(blockedLane.locator('.risk-badge').first()).toContainText(/Risk/i);
    await expect(blockedLane.locator('.flow-why-badge').first()).toBeVisible();

    await blockedLane.locator('.flow-action-btn', { hasText: 'Acknowledge' }).first().click();
    await blockedLane.locator('.flow-action-btn.warn', { hasText: 'Escalate' }).first().click();

    await expect(page.locator('#flow-kpi-escalations')).not.toHaveText('0');
    await expect(page.locator('#flow-alert-feed .flow-alert-item').first()).toBeVisible();
  });

  test('exposes health API endpoint', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:8099/health');
    expect(response.ok()).toBeTruthy();

    const payload = await response.json();
    expect(payload.status).toBe('healthy');
    expect(payload.name).toBe('command-centre');
  });
});
