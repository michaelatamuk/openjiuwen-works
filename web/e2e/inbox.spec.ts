import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

type E2EState = { token?: string; port: number; home: string };

function state(): E2EState {
  return JSON.parse(readFileSync(STATE, "utf8")) as E2EState;
}

function appPath(): string {
  const { token } = state();
  return token ? `/?bootstrap=${encodeURIComponent(token)}` : "/";
}

test("duplicate signals can be merged from the queue", async ({ page, request }) => {
  const { home, port, token } = state();
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  for (const ref of ["E2E-DUP-1", "E2E-DUP-2"]) {
    const response = await request.post(`http://127.0.0.1:${port}/api/v1/tasks`, {
      headers,
      data: {
        ref,
        title: "the same duplicate inbox case",
        kind: "manual",
        product: "Fixture",
        repo: `${home}/repo`,
      },
    });
    expect(response.ok()).toBeTruthy();
  }

  await page.goto(appPath());
  const inbox = page.getByRole("region", { name: "Possible duplicates" });
  await expect(inbox).toBeVisible();
  await expect(inbox).toContainText("the same duplicate inbox case");

  await inbox.getByRole("button", { name: "Merge" }).first().click();

  await expect(page.getByText("Merged the duplicate into the older task.")).toBeVisible();
});
