const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: {
    timeout: 15_000
  },
  use: {
    baseURL: "http://127.0.0.1:4181",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "npm run serve:docs",
    url: "http://127.0.0.1:4181",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
