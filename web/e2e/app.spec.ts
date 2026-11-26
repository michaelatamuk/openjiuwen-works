import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

function appPath(): string {
  const state = JSON.parse(readFileSync(STATE, "utf8")) as { token?: string };
  return state.token ? `/?bootstrap=${encodeURIComponent(state.token)}` : "/";
}

test("queue → story → evidence → release", async ({ page }) => {
  await page.goto(appPath());
  await expect(page.getByRole("complementary", { name: "Queue" })).toBeVisible();
  await page.getByRole("button", { name: /A proved fix/ }).click();
  await expect(page.getByRole("heading", { name: "Ready for release" })).toBeVisible();

  await page.getByRole("tab", { name: "Evidence" }).click();
  await expect(page.getByText("Run metadata")).toBeVisible();
  await expect(page.getByText("Runtime artifacts")).toBeVisible();

  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByText("Plain-language summary")).toBeVisible();
  await page.getByRole("tab", { name: "Technical" }).click();

  await page.getByRole("tab", { name: "Release" }).click();
  await expect(page.getByText("Release packet")).toBeVisible();
});

test("settings lists devices and starts pairing", async ({ page }) => {
  await page.goto(appPath());
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Devices" })).toBeVisible();
  await page.getByRole("button", { name: "Pair a phone" }).click();
  await expect(page.getByText(/expires in 300s/)).toBeVisible();
});
