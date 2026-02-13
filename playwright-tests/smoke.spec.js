const { test, expect } = require('@playwright/test');

test('example.com title contains Example Domain', async ({ page }) => {
  await page.goto('https://example.com');
  await expect(page).toHaveTitle(/Example Domain/);
});
