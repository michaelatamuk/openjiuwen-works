import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

type E2EState = { token?: string; port: number };

function state(): E2EState {
  return JSON.parse(readFileSync(STATE, "utf8")) as E2EState;
}

function appPath(): string {
  const { token } = state();
  return token ? `/?bootstrap=${encodeURIComponent(token)}` : "/";
}

test("adding context writes a note into the session thread", async ({ page }) => {
  await page.goto(appPath());
  await expect(page.getByRole("complementary", { name: "Queue" })).toBeVisible();
  await page.getByRole("button", { name: /A proved fix/ }).click();
  await page.getByRole("tab", { name: "Session" }).click();

  const askMode = page.getByRole("button", { name: "Ask", exact: true });
  if (await askMode.isVisible().catch(() => false)) {
    await askMode.click();
  }

  const note = "Checked the flaky test by hand, it passes now.";
  await page.getByPlaceholder("Add context to this run...").fill(note);
  await page.getByRole("button", { name: "Add context" }).click();
  await expect(page.getByText(note)).toBeVisible();
});

test("a paired device can be revoked from Settings", async ({ page, request }) => {
  const { token, port } = state();
  const headers = { Authorization: `Bearer ${token ?? ""}` };
  const paired = await request.post(`http://127.0.0.1:${port}/api/v1/admin/pair`, {
    headers,
    data: { label: "e2e-phone" },
  });
  expect(paired.ok()).toBe(true);
  const { code } = (await paired.json()) as { code: string };
  const redeemed = await request.post(`http://127.0.0.1:${port}/api/v1/pair`, {
    data: { code, label: "e2e-phone" },
  });
  expect(redeemed.ok()).toBe(true);

  await page.goto(appPath());
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Devices" })).toBeVisible();
  await expect(page.getByText("e2e-phone")).toBeVisible();

  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("No devices paired.")).toBeVisible();
});
