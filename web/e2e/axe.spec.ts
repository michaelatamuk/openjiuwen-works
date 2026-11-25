import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

function appPath(): string {
  const state = JSON.parse(readFileSync(STATE, "utf8")) as { token?: string };
  return state.token ? `/?bootstrap=${encodeURIComponent(state.token)}` : "/";
}

async function expectNoSeriousViolations(page: Page, screen: string): Promise<void> {
  await page.waitForTimeout(150);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const blockers = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );
  const detail = blockers
    .map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.nodes
          .slice(0, 3)
          .map((node) => node.target.join(" "))
          .join(", ")}`,
    )
    .join("; ");
  expect(blockers, `${screen}: ${detail}`).toEqual([]);
}

test("story, evidence, release, session and settings have no serious axe violations", async ({
  page,
}) => {
  await page.goto(appPath());
  await expect(page.getByRole("complementary", { name: "Queue" })).toBeVisible();
  await expectNoSeriousViolations(page, "queue");

  await page.getByRole("button", { name: /A proved fix/ }).click();
  await expect(page.getByRole("heading", { level: 2 })).toContainText("Ready for release");
  await expectNoSeriousViolations(page, "story");

  await page.getByRole("tab", { name: "Evidence" }).click();
  await expect(page.getByText("Run metadata")).toBeVisible();
  await expectNoSeriousViolations(page, "evidence");

  await page.getByRole("tab", { name: "Release" }).click();
  await expect(page.getByText("Release packet")).toBeVisible();
  await expectNoSeriousViolations(page, "release");

  await page.getByRole("tab", { name: "Session" }).click();
  await expect(page.getByRole("tab", { name: "Session" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expectNoSeriousViolations(page, "session");

  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expectNoSeriousViolations(page, "settings");
});
