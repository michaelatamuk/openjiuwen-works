import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Opt-in visual snapshots. They are not a required gate: baselines are platform-specific, so run
 * them manually on a clean machine:
 *
 *   $env:WORKS_VISUAL=1; npm run e2e:visual
 *   $env:WORKS_VISUAL=1; npm run e2e:visual -- --update-snapshots
 */

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

test.skip(process.env.WORKS_VISUAL !== "1", "set WORKS_VISUAL=1 to record or compare snapshots");

function appPath(): string {
  const state = JSON.parse(readFileSync(STATE, "utf8")) as { token?: string };
  return state.token ? `/?bootstrap=${encodeURIComponent(state.token)}` : "/";
}

for (const theme of ["light", "dark"] as const) {
  test(`story, evidence and release in ${theme}`, async ({ page }) => {
    await page.addInitScript((value) => {
      localStorage.setItem("works.theme", value);
    }, theme);
    await page.goto(appPath());
    await expect(page.getByRole("complementary", { name: "Queue" })).toBeVisible();
    await page.getByRole("button", { name: /A proved fix/ }).click();
    await expect(page.getByRole("heading", { level: 2 })).toContainText("Ready for release");
    await expect(page).toHaveScreenshot(`story-${theme}.png`, { maxDiffPixelRatio: 0.01 });

    await page.getByRole("tab", { name: "Evidence" }).click();
    await expect(page.getByText("Run metadata")).toBeVisible();
    await expect(page).toHaveScreenshot(`evidence-${theme}.png`, { maxDiffPixelRatio: 0.01 });

    await page.getByRole("tab", { name: "Release" }).click();
    await expect(page.getByText("Release packet")).toBeVisible();
    await expect(page).toHaveScreenshot(`release-${theme}.png`, { maxDiffPixelRatio: 0.01 });
  });
}
