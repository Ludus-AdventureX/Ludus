/**
 * Playwright globalTeardown: stop the analysis worker started in globalSetup.
 *
 * Separate module because Playwright expects a default export per hook; the
 * handle travels through the pid file so this works even when setup and teardown
 * run in different module instances.
 */

import { stopWorker } from "./analysis-worker-process";

export default async function globalTeardown(): Promise<void> {
  await stopWorker();
}
