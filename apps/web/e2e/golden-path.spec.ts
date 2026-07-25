import { expect, test } from "@playwright/test";

type ApiEnvelope<T> = {
  data: T;
  meta?: { idempotencyReplay?: boolean };
};

type SimulationRunPayload = {
  simulationRunId: string;
  workspaceId: string;
  graphId: string;
  engineVersion: string;
  inputHash: string;
  recommendedOptionId: string | null;
  recommendationShift: string;
  convergenceStatus: string;
  optionScores: { optionId: string; score: number }[];
  topDrivers: { nodeId: string; scoreDelta: number }[];
};

const sha256InputHash = /^sha256:[0-9a-f]{64}$/;

function valueAfterLabel(label: string) {
  return `dt:text-is("${label}") + dd`;
}

test("guest simulation golden path uses the real same-origin API", async ({ page }) => {
  await page.goto("/");

  const demoLink = page.getByRole("link", { name: /Guest Simulation Demo/i });
  await expect(demoLink).toBeVisible();
  await demoLink.click();

  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "Simulation Demo" })).toBeVisible();
  await expect(page.getByText(/Technical Alpha/).first()).toBeVisible();

  const runButton = page.getByRole("button", { name: "Run Simulation" });
  await expect(runButton).toBeEnabled({ timeout: 30_000 });

  const postRunResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/workspaces/") &&
      response.url().includes("/simulations/") &&
      response.url().endsWith("/runs"),
  );
  const replayResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      response.url().includes("/api/workspaces/") &&
      response.url().includes("/simulations/") &&
      /\/runs\/[^/]+$/.test(new URL(response.url()).pathname),
  );

  await runButton.click();

  const postRun = await postRunResponse;
  expect(postRun.status()).toBe(201);
  const postPayload = (await postRun.json()) as ApiEnvelope<SimulationRunPayload>;
  expect(postPayload.data.engineVersion).toBe("sim-engine-1.1.0");
  expect(postPayload.data.inputHash).toMatch(sha256InputHash);
  expect(postPayload.data.optionScores.length).toBeGreaterThan(0);
  expect(Array.isArray(postPayload.data.topDrivers)).toBe(true);

  const replay = await replayResponse;
  expect(replay.status()).toBe(200);
  const replayPayload = (await replay.json()) as ApiEnvelope<SimulationRunPayload>;
  expect(replayPayload.data).toEqual(postPayload.data);

  await expect(page.getByRole("heading", { name: /Run/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Option Scores" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Sensitivity/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Replay/ })).toBeVisible();

  await expect(page.locator(valueAfterLabel("Run ID"))).toHaveText(postPayload.data.simulationRunId);
  await expect(page.locator(valueAfterLabel("Replay Run ID"))).toHaveText(postPayload.data.simulationRunId);
  await expect(page.locator(valueAfterLabel("Input Hash"))).toHaveText(postPayload.data.inputHash);
  await expect(page.locator(valueAfterLabel("Replay Input Hash"))).toHaveText(postPayload.data.inputHash);
  await expect(page.locator(valueAfterLabel("Engine Version"))).toHaveText("sim-engine-1.1.0");
  await expect(page.getByText(postPayload.data.recommendationShift).first()).toBeVisible();
});



