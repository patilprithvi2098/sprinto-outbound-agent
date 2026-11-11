import { defineConfig, devices } from "@playwright/test";

// ADAPT: port, dev command and ready URL to the project.
// Next.js allows one dev server per project, so reuse the one on the usual port if it is already running.
const PORT = Number(process.env.PW_PORT ?? 8321);

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // Runs in the user's installed Google Chrome (channel "chrome"), not Playwright's bundled engines.
  // Each run gets a clean temporary profile, so tests never touch real cookies, history or logins.
  projects: [
    { name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } },
    { name: "chrome-375", use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true } },
  ],
  webServer: {
    command: "python3 app/server.py",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
