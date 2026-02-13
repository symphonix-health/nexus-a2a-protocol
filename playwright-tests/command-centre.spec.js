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
    await expect(page.locator('#flow-lane-now')).toBeVisible();
    await expect(page.locator('#timeline-container')).toBeVisible();

    await expect(page.locator('#connection-text')).toHaveText(/Connected|Disconnected|Connecting/);
  });

  test('exposes health API endpoint', async ({ request }) => {
    const response = await request.get('http://127.0.0.1:8099/health');
    expect(response.ok()).toBeTruthy();

    const payload = await response.json();
    expect(payload.status).toBe('healthy');
    expect(payload.name).toBe('command-centre');
  });
});
