import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const repoRoot = path.resolve(__dirname, "../..");
const apiRoot = path.join(repoRoot, "services", "api");
const apiPort = Number(process.env.E2E_API_PORT ?? 8010);
const webPort = Number(process.env.E2E_WEB_PORT ?? 3010);
const apiOrigin = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${apiPort}`;
const webOrigin = process.env.E2E_WEB_ORIGIN ?? `http://127.0.0.1:${webPort}`;
const apiCommand =
  process.env.E2E_API_COMMAND ??
  `python -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`;
const webCommand =
  process.env.E2E_WEB_COMMAND ??
  `pnpm --dir apps/web build && pnpm --dir apps/web start --hostname 127.0.0.1 --port ${webPort}`;
const browserChannel = process.env.E2E_BROWSER_CHANNEL;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  // The analysis golden path drives a real multi-stage run end to end.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  // The analysis worker has no HTTP port, so it cannot be a `webServer` entry;
  // it is spawned in globalSetup and killed in teardown. Without it a run stays
  // `queued` forever - the exact failure this suite now guards.
  globalSetup: "./e2e/analysis-worker-process.ts",
  globalTeardown: "./e2e/analysis-worker-teardown.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: webOrigin,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        ...(browserChannel ? { channel: browserChannel } : {}),
      },
    },
  ],
  webServer: [
    {
      command: apiCommand,
      cwd: process.env.E2E_API_CWD ?? apiRoot,
      url: `${apiOrigin}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH ?? apiRoot,
        POSTGRES_HOST: process.env.POSTGRES_HOST ?? "127.0.0.1",
        POSTGRES_PORT: process.env.POSTGRES_PORT ?? "5432",
        POSTGRES_DB: process.env.POSTGRES_DB ?? "decision_lab",
        POSTGRES_USER: process.env.POSTGRES_USER ?? "decision_lab",
        POSTGRES_PASSWORD: process.env.POSTGRES_PASSWORD ?? "decision_lab_dev",
        DATABASE_URL: process.env.DATABASE_URL ?? "",
        ENABLE_GUEST_ALPHA: process.env.ENABLE_GUEST_ALPHA ?? "true",
        // Registration is invite-gated. This is sha256("e2e-alpha-invite") and
        // MUST stay in sync with SIGNUP_CODE in analysis-golden-path.spec.ts;
        // an unset variable would close registration and the golden path could
        // never authenticate.
        SIGNUP_INVITE_CODE_HASHES:
          process.env.SIGNUP_INVITE_CODE_HASHES ??
          "17252925e4055c8a58fd43516e1005d5dda46216153914bdc23d266776049506",
        FIXTURE_MODE: process.env.FIXTURE_MODE ?? "true",
        AUTH_ALLOWED_ORIGINS:
          process.env.AUTH_ALLOWED_ORIGINS ?? JSON.stringify([webOrigin]),
        AUTH_COOKIE_SECURE: process.env.AUTH_COOKIE_SECURE ?? "false",
        AUTH_JWT_SECRET:
          process.env.AUTH_JWT_SECRET ?? "e2e-local-insecure-jwt-secret-change-me",
      },
    },
    {
      command: webCommand,
      cwd: repoRoot,
      url: webOrigin,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        API_PROXY_TARGET: process.env.API_PROXY_TARGET ?? apiOrigin,
        NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "/api",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
