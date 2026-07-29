import { expect, test, type Page } from "@playwright/test";

/**
 * The analysis golden path: authenticate through the invite gate, ask a
 * question, launch a formal run, and watch the six-stage indicator advance to a
 * terminal verdict.
 *
 * This is the path the product owner reported as "the worker does not work and
 * the whole flow does not run", and until now `e2e/` covered only the simulation
 * demo - so nothing in CI would have caught it. It exercises three processes at
 * once (web, api, analysis worker) in fixture mode, which is also a regression
 * test for the key-free path itself.
 *
 * What it deliberately does NOT do: assert a specific analysis conclusion.
 * Fixture output is deterministic but it is placeholder content, and asserting
 * on it would turn a fixture into a pretend product claim.
 */

const QUESTION =
  "资金与研发资源有限，球形机器人项目应优先进入救援市场还是家庭服务市场？";

// MUST match sha256(SIGNUP_CODE) configured as SIGNUP_INVITE_CODE_HASHES in
// playwright.config.ts. Registration is the only way in now that the guest door
// is closed, so an unmatched code would leave the whole path unable to start.
const SIGNUP_CODE = "e2e-alpha-invite";

const STAGES = ["planning", "retrieving", "analyzing", "criticizing", "synthesizing", "validating"];

/**
 * Register a fresh account through /enter. A unique email keeps every test run
 * independent (register commits), and landing back on the shell home confirms
 * the session cookie is set before anything tries to create a case.
 */
async function registerFreshAccount(page: Page): Promise<void> {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.test`;
  await page.goto("/enter");

  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill("e2e-strong-password");
  await page.getByLabel("邀请码").fill(SIGNUP_CODE);

  // Wait for the redirect the /enter route performs on success: a failed invite
  // gate would keep us on /enter with an alert, so this both drives and asserts
  // that the account was admitted.
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/enter"), { timeout: 30_000 }),
    page.getByRole("button", { name: "创建账号并进入" }).click(),
  ]);
}

test("analysis golden path: launch a run and watch the stages advance", async ({ page }) => {
  test.setTimeout(180_000);

  // 0. Authenticate through the invite gate; the create flow needs a session.
  await registerFreshAccount(page);

  // 1. Create a decision case from the first screen (no marketing detour).
  await page.goto("/");
  const composer = page.getByRole("textbox").first();
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await composer.fill(QUESTION);
  // Assert the value landed before clicking: a click that races the fill was the
  // one intermittent artefact this spec had, and it never reproduced in a real
  // browser. Waiting on the value removes the race deterministically.
  await expect(composer).toHaveValue(QUESTION);
  // Anchored name on purpose: a loose /创建/ also matches the masthead's
  // "尚未创建决策项目" drawer trigger, which appears earlier in the DOM and would
  // open the project drawer instead of creating anything.
  const create = page.getByRole("button", { name: /^建立决策项目/ });
  await expect(create).toBeEnabled();
  await Promise.all([
    page.waitForURL(/\/cases\/[^/]+\?ws=/, { timeout: 60_000 }),
    create.click(),
  ]);

  // 2. Launch the formal run.
  const launch = page.getByRole("button", { name: /发起聚焦深度分析/ });
  await expect(launch).toBeEnabled({ timeout: 30_000 });
  await launch.click();

  // 3. The six-stage indicator must appear - this is the answer to "where is my
  //    analysis right now?", and it must be present BEFORE the run finishes.
  const stepper = page.locator("[data-analysis-stepper]");
  await expect(stepper).toBeVisible({ timeout: 60_000 });
  for (const stage of STAGES) {
    await expect(stepper.locator(`[data-stage="${stage}"]`)).toHaveCount(1);
  }

  // 4. A real progress bar with real aria values (never a fake timer).
  const bar = page.getByRole("progressbar", { name: "分析进度" });
  await expect(bar).toBeVisible();
  await expect(bar).toHaveAttribute("aria-valuemin", "0");
  await expect(bar).toHaveAttribute("aria-valuemax", "100");

  // 5. The run reaches a terminal verdict. `ready` and `blocked` are BOTH
  //    acceptable: a blocked run is an honest quality-gate refusal, not a
  //    failure, and the test must not pressure the gate into passing.
  const terminal = page.locator("[data-analysis-terminal]");
  await expect(terminal).toHaveCount(1, { timeout: 150_000 });
  const verdict = await terminal.getAttribute("data-analysis-terminal");
  expect(["ready", "blocked", "needs_attention"]).toContain(verdict);

  // 6. Whatever the verdict, every stage must have left the "not started" state:
  //    a run that never advanced is the exact bug this spec exists to catch.
  const pendingStages = await stepper.locator('[data-stage-state="pending"]').count();
  expect(pendingStages).toBe(0);

  // 7. The trace must carry at least one stage digest (the visible thinking).
  await expect(stepper.locator(".stepper-digest").first()).toBeVisible();
});

test("without a workspace anchor the panel refuses to fabricate a run", async ({ page }) => {
  // Honest gap state: no ?ws= means no launch affordance at all. This holds
  // whether or not a session exists, so it does not authenticate first.
  await page.goto("/cases/00000000-0000-4000-8000-000000000000");
  await expect(page.locator('[data-analysis-launch="gap"]').first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("button", { name: /发起聚焦深度分析/ })).toHaveCount(0);
});
