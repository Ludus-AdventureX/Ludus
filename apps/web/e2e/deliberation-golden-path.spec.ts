import { expect, test, type Page } from "@playwright/test";

/**
 * The deliberation council golden path (CCR-20260804-DELIB-01, Wave 4):
 * register, create a case, run the fixture analysis to a terminal verdict,
 * then open a council on the G page and drive the FULL intervenable loop:
 * declare a subjective factor -> watch witness openings -> interject and
 * challenge a witness -> accept a pending proposal -> confirm a moderator
 * nomination -> outcome with conditional projections and the fixed
 * "not an exact prediction" disclaimer.
 *
 * Everything numeric is engine-computed; this spec deliberately asserts NO
 * probability wording anywhere on the board (the red-line battery's UI half).
 * Fixture mode keeps the whole path deterministic and key-free: the fixture
 * analysis emits exactly three packets (supporting/neutral/opposing), so the
 * council's opening, the cross-examination proposal and the moderator
 * nomination all fire by construction.
 */

const QUESTION =
  "资金与研发资源有限，球形机器人项目应优先进入救援市场还是家庭服务市场？";

// MUST match sha256(SIGNUP_CODE) configured in playwright.config.ts (same gate
// as analysis-golden-path.spec.ts).
const SIGNUP_CODE = "e2e-alpha-invite";

const SUBJECTIVE_LABEL = "对手降价意愿";
const SUBJECTIVE_STATEMENT = "直觉判断：主要竞品会在九十天内跟进降价。";

async function registerFreshAccount(page: Page): Promise<void> {
  const email = `e2e-delib-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.test`;
  await page.goto("/enter");

  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill("e2e-strong-password");
  await page.getByLabel("邀请码").fill(SIGNUP_CODE);

  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/enter"), { timeout: 30_000 }),
    page.getByRole("button", { name: "创建账号并进入" }).click(),
  ]);
}

test("deliberation golden path: intervene, adopt, nominate, then an engine verdict", async ({
  page,
}) => {
  test.setTimeout(300_000);

  // 0. Authenticate, create the case, run the fixture analysis to terminal so
  //    the council has a frozen objective basis (research packets).
  await registerFreshAccount(page);
  await page.goto("/");
  const composer = page.getByRole("textbox").first();
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await composer.fill(QUESTION);
  await expect(composer).toHaveValue(QUESTION);
  const create = page.getByRole("button", { name: /^建立决策项目/ });
  await expect(create).toBeEnabled();
  await Promise.all([
    page.waitForURL(/\/cases\/[^/]+\?ws=/, { timeout: 60_000 }),
    create.click(),
  ]);

  // The launch panel lives in the E (证据) workspace, not the default Q view.
  const spine = page.getByRole("navigation", { name: "决策生命周期" });
  await spine.getByRole("button", { name: /证据/ }).click();
  const launch = page.getByRole("button", { name: "发起分析" });
  await expect(launch).toBeEnabled({ timeout: 30_000 });
  await launch.click();
  const terminal = page.locator("[data-analysis-terminal]");
  await expect(terminal).toHaveCount(1, { timeout: 180_000 });

  // 1. Move to the G page (推演 workspace); the council board must mount in
  //    its honest creation state because the case now has a factor basis.
  await spine.getByRole("button", { name: /推演/ }).click();
  const board = page.locator("[data-deliberation-board]");
  await expect(board).toHaveAttribute("data-deliberation-board", "create", {
    timeout: 30_000,
  });

  // 2. Declare a subjective factor BEFORE creation: it must enter the graph
  //    as an assumed, Human-signed factor, never as evidence.
  await page.getByLabel("主观因子名称").fill(SUBJECTIVE_LABEL);
  await page.getByLabel("主观因子陈述").fill(SUBJECTIVE_STATEMENT);
  await page.getByRole("button", { name: "加入声明" }).click();
  await expect(page.locator(`[data-declared-factor="${SUBJECTIVE_LABEL}"]`)).toBeVisible();

  // Two rounds: opening + one cross-examination round, then the verdict.
  await page.getByLabel("轮次预算").selectOption("2");
  await page.getByRole("button", { name: "创建议会并开始推演" }).click();

  // 3. The run panel appears and the fixture worker opens round one: every
  //    factor (3 objective + 1 subjective) gets a witness statement.
  await expect(board).toHaveAttribute("data-deliberation-board", "run", {
    timeout: 60_000,
  });
  const witnessMessages = page.locator('.deliberation-transcript [data-speaker="witness"]');
  await expect(witnessMessages.first()).toBeVisible({ timeout: 60_000 });
  await expect
    .poll(async () => witnessMessages.count(), { timeout: 60_000 })
    .toBeGreaterThanOrEqual(4);
  // The subjective witness must disclose its assumed/Human nature verbatim.
  await expect(page.getByText(/主观判断「对手降价意愿」/)).toBeVisible();

  // 4. Interventions are recorded synchronously: interject, then challenge a
  //    specific witness. Both surface as user-stamped transcript entries.
  const intervention = page.getByLabel("介入文本");
  await intervention.fill("请评估对手降价对首年收入的影响。");
  await page.getByRole("button", { name: "插话", exact: true }).click();
  const userMessages = page.locator('.deliberation-transcript [data-speaker="user"]');
  await expect(userMessages.first()).toBeVisible({ timeout: 30_000 });

  await intervention.fill("认证门槛到底有多高？请持证人正面回答。");
  await page.getByLabel("质询目标因子").selectOption({ index: 1 });
  await page.getByRole("button", { name: "质询该持证人" }).click();
  await expect
    .poll(async () => userMessages.count(), { timeout: 30_000 })
    .toBeGreaterThanOrEqual(2);

  // 5. The cross-examination round lands pending proposals (opposing-side
  //    witnesses ask to weaken the strongest opposite driver). Adopt the
  //    first — the accepted projection rides into the verdict — then reject
  //    every remaining one: both decision paths must work, and a rejected
  //    proposer is exactly what the outcome's dissent log records.
  const firstProposal = page.locator("[data-proposal-id]").first();
  await expect(firstProposal).toBeVisible({ timeout: 90_000 });
  await firstProposal.getByRole("button", { name: "采纳" }).click();
  // Poll until the accepted entry disappears, then reject whatever remains.
  await expect
    .poll(
      async () => {
        const proposals = page.locator("[data-proposal-id]");
        const count = await proposals.count();
        if (count > 0) {
          await proposals.first().getByRole("button", { name: "驳回" }).click();
        }
        return count;
      },
      { timeout: 60_000 }
    )
    .toBe(0);

  // 6. The moderator nomination for the most sensitive uncovered driver sits
  //    pending (run parks at awaiting_user) and NEVER auto-activates: it is
  //    gone only after the explicit confirmation flow below.
  const nomination = page.locator("[data-nomination-id]").first();
  await expect(nomination).toBeVisible({ timeout: 60_000 });
  await nomination.getByRole("button", { name: "我来声明" }).click();
  await nomination.getByLabel("提名判断陈述").fill("我对这个因子有内部判断：它的真实强度被低估了。");
  await nomination.getByRole("button", { name: "确认并声明" }).click();
  await expect
    .poll(async () => page.locator("[data-nomination-id]").count(), { timeout: 60_000 })
    .toBe(0);

  // 7. Budget exhausted -> the verdict round: conditional projections, flip
  //    conditions and the fixed disclaimer. Status flips to complete.
  const outcome = page.locator('[data-deliberation-outcome="ready"]');
  await expect(outcome).toBeVisible({ timeout: 120_000 });
  await expect(outcome.getByText(/不代表精确预测/)).toBeVisible();
  await expect(outcome.locator(".deliberation-projections li").first()).toBeVisible();
  await expect(board).toHaveAttribute("data-deliberation-status", "complete", {
    timeout: 30_000,
  });

  // 8. Red line (AGENTS §7): the board never renders probability wording.
  const boardText = await board.textContent();
  expect(boardText ?? "").not.toMatch(/成功概率|正确概率|成功的可能性为/);
});
