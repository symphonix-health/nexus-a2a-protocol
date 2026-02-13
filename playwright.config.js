const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './playwright-tests',
  fullyParallel: false,
  retries: 0,
  use: {
    headless: true,
  },
});
