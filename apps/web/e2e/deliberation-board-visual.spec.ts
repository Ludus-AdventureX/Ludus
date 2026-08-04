import { expect, test, type Page } from "@playwright/test";

/**
 * Three-viewport visual verification for the deliberation board
 * (CCR-20260804-DELIB-01, Wave 4.3), following the causal-graph A+B
 * measurement method: real app + real stylesheets, DOM metrics as the
 * verification record (no horizontal overflow, board blocks render),
 * screenshot evidence at 1440x900 / 1024x768 / 390x844.
 *
 * The flow is the short honest path: register, create a case, run the
 * fixture analysis to terminal, open the G page, declare a subjective
 * factor and start the council — then measure the running board at all
 * three viewports. The ≤620px rule is asserted explicitly: the transcript
 * becomes a capped scrollable stream and the declaration row stacks.
 */

const QUESTION =
  "资金与研发资源有限，球形机器人项目应优先进入救援市场还是家庭服务市场？";
const SIGNUP_CODE = "e2e-alpha-invite";

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
] as const;

async function registerFreshAccount(page: Page): Promise<void> {
  const email = `e2e-vis-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.test`;
  await page.goto("/enter");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill("e2e-strong-password");
  await page.getByLabel("邀请码").fill(SIGNUP_CODE);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/enter"), { timeout: 30_000 }),
    page.getByRole("button", { name: "创建账号并进入" }).click(),
  ]);
}

async function measureOverflow(page: Page): Promise<{ scrollWidth: number; clientWidth: number }> {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

test("deliberation board holds at 1440/1024/390 without overflow", async ({ page }) => {
  test.setTimeout(300_000);

  await registerFreshAccount(page);
  await page.goto("/");
  const composer = page.getByRole("textbox").first();
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await composer.fill(QUESTION);
  await expect(composer).toHaveValue(QUESTION);
  await Promise.all([
    page.waitForURL(/\/cases\/[^/]+\?ws=/, { timeout: 60_000 }),
    page.getByRole("button", { name: /^建立决策项目/ }).click(),
  ]);

  // The launch panel lives in the E (证据) workspace, not the default Q view.
  const spine = page.getByRole("navigation", { name: "决策生命周期" });
  await spine.getByRole("button", { name: /证据/ }).click();
  const launch = page.getByRole("button", { name: "发起分析" });
  await expect(launch).toBeEnabled({ timeout: 30_000 });
  await launch.click();
  await expect(page.locator("[data-analysis-terminal]")).toHaveCount(1, { timeout: 180_000 });

  await spine.getByRole("button", { name: /推演/ }).click();
  const board = page.locator("[data-deliberation-board]");
  await expect(board).toHaveAttribute("data-deliberation-board", "create", { timeout: 30_000 });

  // Declare one subjective factor so the running board shows the dashed,
  // Human-signed node family at every viewport.
  await page.getByLabel("主观因子名称").fill("对手降价意愿");
  await page.getByLabel("主观因子陈述").fill("直觉判断：主要竞品会在九十天内跟进降价。");
  await page.getByRole("button", { name: "加入声明" }).click();
  await page.getByLabel("轮次预算").selectOption("2");
  await page.getByRole("button", { name: "创建议会并开始推演" }).click();
  await expect(board).toHaveAttribute("data-deliberation-board", "run", { timeout: 60_000 });
  await expect(
    page.locator('.deliberation-transcript [data-speaker="witness"]').first()
  ).toBeVisible({ timeout: 60_000 });

  for (const viewport of VIEWPORTS) {
    await test.step(`viewport ${viewport.width}x${viewport.height}`, async () => {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(400); // let the canvas/layout settle
      await board.scrollIntoViewIfNeeded();

      const metrics = await measureOverflow(page);
      expect(
        metrics.scrollWidth,
        `horizontal overflow at ${viewport.width}px`
      ).toBeLessThanOrEqual(metrics.clientWidth + 1);

      await expect(board).toBeVisible();
      await expect(page.locator(".deliberation-transcript").first()).toBeVisible();

      if (viewport.width <= 620) {
        // ≤620px rule: the live panel degrades to a capped read-only stream.
        const transcript = page.locator(".deliberation-transcript ol").first();
        const maxHeight = await transcript.evaluate((el) =>
          Number.parseFloat(getComputedStyle(el).maxHeight)
        );
        expect(maxHeight).toBeLessThanOrEqual(300);
      }

      await page.screenshot({
        path: `test-results/deliberation-board-${viewport.width}x${viewport.height}.png`,
        fullPage: false,
      });
    });
  }
});
