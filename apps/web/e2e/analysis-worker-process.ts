/**
 * Playwright global setup/teardown for the analysis worker.
 *
 * The analysis golden path needs a THIRD process: without the worker the run
 * stays `queued` forever, which is exactly the failure the product owner hit.
 * The worker is a DB-queue poller with no HTTP port, so it cannot be a
 * `webServer` entry (Playwright waits on a url/port); it is spawned here and
 * killed in teardown.
 *
 * Fixture mode keeps this deterministic and free: no model key, no network.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

const repoRoot = path.resolve(__dirname, "../../..");
const apiRoot = path.join(repoRoot, "services", "api");

// Setup and teardown may run in different module instances, so the handle is
// passed through a pid file rather than a module-level variable.
export const WORKER_PID_FILE = path.join(tmpdir(), "ludus-e2e-analysis-worker.pid");

let worker: ChildProcess | undefined;

function workerEnv(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    PYTHONPATH: process.env.PYTHONPATH ?? apiRoot,
    POSTGRES_HOST: process.env.POSTGRES_HOST ?? "127.0.0.1",
    POSTGRES_PORT: process.env.POSTGRES_PORT ?? "5432",
    POSTGRES_DB: process.env.POSTGRES_DB ?? "decision_lab",
    POSTGRES_USER: process.env.POSTGRES_USER ?? "decision_lab",
    POSTGRES_PASSWORD: process.env.POSTGRES_PASSWORD ?? "decision_lab_dev",
    // MODEL_PROVIDER must be explicit: FIXTURE_MODE alone still selects the live
    // provider whenever a key happens to be present in the environment.
    MODEL_PROVIDER: "fixture",
    FIXTURE_MODE: "true",
    MODEL_API_KEY: "",
    EXA_API_KEY: "",
    FIRECRAWL_API_KEY: "",
    TAVILY_API_KEY: "",
    WORKER_POLL_INTERVAL_SECONDS: "1.0",
    WORKER_LOG_LEVEL: "INFO",
  };
}

export default async function globalSetup(): Promise<void> {
  if (process.env.E2E_SKIP_WORKER === "true") return;
  const command = process.env.E2E_WORKER_COMMAND ?? "python";
  const args = process.env.E2E_WORKER_COMMAND
    ? []
    : ["-m", "app.workers.run"];
  worker = spawn(command, args, {
    cwd: apiRoot,
    env: workerEnv(),
    stdio: "inherit",
    shell: Boolean(process.env.E2E_WORKER_COMMAND),
  });
  worker.on("error", (error) => {
    console.error("[e2e] analysis worker failed to start:", error);
  });
  if (worker.pid) {
    writeFileSync(WORKER_PID_FILE, String(worker.pid), "utf8");
  }
  // The worker polls; there is no readiness endpoint to wait on. One poll
  // interval is enough for it to be draining the queue by the time a test
  // creates a run.
  await new Promise((resolve) => setTimeout(resolve, 2000));
}

export async function stopWorker(): Promise<void> {
  if (worker && !worker.killed) {
    worker.kill();
  }
  if (!existsSync(WORKER_PID_FILE)) return;
  try {
    const pid = Number(readFileSync(WORKER_PID_FILE, "utf8").trim());
    if (Number.isFinite(pid) && pid > 0) {
      process.kill(pid);
    }
  } catch {
    // Already gone: nothing to reclaim.
  } finally {
    rmSync(WORKER_PID_FILE, { force: true });
  }
}
