const path = require('path');
const { pathToFileURL } = require('url');
const { test, expect } = require('@playwright/test');

test('local fixture renders and button click updates result', async ({ page }) => {
  const htmlPath = path.resolve(__dirname, '..', 'test_page.html');
  const htmlUrl = pathToFileURL(htmlPath).href;

  await page.goto(htmlUrl);

  await expect(page).toHaveTitle('MCP Browser Test');
  await expect(page.getByRole('heading', { name: 'MCP Browser Server Test' })).toBeVisible();

  await page.getByRole('button', { name: 'Click Me' }).click();
  await expect(page.locator('#result')).toHaveText('Button clicked successfully!');
});
