import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";

// These journeys need something the default CI does not have: a GitHub token or a model key.
// They are opt-in so a laptop can prove them without turning a secret into a required check.
const ASK = process.env.WORKS_E2E_ASK === "1";
const IMPORT = process.env.WORKS_E2E_GITHUB === "1";
const REPOSITORY = process.env.WORKS_E2E_GITHUB_REPO || "michaelatamuk/works-calc-demo";

const STATE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".e2e-state.json");

type E2EState = { token?: string; port: number; home: string };

function state(): E2EState {
  return JSON.parse(readFileSync(STATE, "utf8")) as E2EState;
}

function api(pathname: string): string {
  return `http://127.0.0.1:${state().port}/api/v1${pathname}`;
}

function headers(): Record<string, string> {
  return { Authorization: `Bearer ${state().token}`, "Content-Type": "application/json" };
}

async function waitForJob(
  request: APIRequestContext,
  jobID: string,
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const response = await request.get(api(`/jobs/${jobID}`));
    const job = (await response.json()) as Record<string, unknown>;
    if (job.status === "succeeded") return job;
    if (job.status === "failed" || job.status === "cancelled") {
      throw new Error(`job ${jobID} ended ${String(job.status)}: ${JSON.stringify(job.result)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`job ${jobID} did not finish`);
}

test("a real GitHub issue becomes a queued task", async ({ request }) => {
  test.skip(!IMPORT, "opt-in: set WORKS_E2E_GITHUB=1 and sign in with gh");

  const { home } = state();
  const response = await request.post(api("/sources"), {
    headers: headers(),
    data: {
      source: "github",
      repository: REPOSITORY,
      product: "Fixture",
      repo: `${home}/repo`,
      limit: 5,
    },
  });
  expect(response.status()).toBe(202);
  const job = ((await response.json()) as { job: { id: string } }).job;

  const finished = await waitForJob(request, job.id);
  const result = finished.result as { found: number; created: number; tasks: string[] };
  expect(result.found).toBeGreaterThan(0);
  expect(result.tasks.length).toBeGreaterThan(0);

  const detail = await request.get(api(`/tasks/${result.tasks[0]}`));
  expect(detail.status()).toBe(200);
  const body = (await detail.json()) as {
    task: { source: { kind: string; ref: string } };
  };
  expect(body.task.source.kind).toBe("tracker");
  expect(body.task.source.ref).toMatch(new RegExp(`^${REPOSITORY}#\\d+$`));
});

test("ask streams a model answer over SSE", async ({ request }) => {
  test.skip(!ASK, "opt-in: set WORKS_E2E_ASK=1 and provide ANTHROPIC_API_KEY or WORKS_MODEL_KEY");

  const listed = await request.get(api("/tasks"));
  const tasks = ((await listed.json()) as { tasks: { id: string; state: string }[] }).tasks;
  expect(tasks.length).toBeGreaterThan(0);
  const subject = tasks.find((task) => task.state === "proved") ?? tasks[0];

  const response = await request.post(api("/ask/stream"), {
    headers: headers(),
    data: { task_id: subject.id, question: "In one sentence: what is the most likely risk here?" },
    timeout: 180_000,
  });
  expect(response.status()).toBe(200);
  const body = await response.text();

  expect(body).not.toMatch(/"type":\s*"error"/);
  expect(body).toMatch(/"type":\s*"delta"/);
  expect(body).toMatch(/"type":\s*"done"/);
  expect(body).toMatch(/"text":\s*"[^"]+"/);
});
