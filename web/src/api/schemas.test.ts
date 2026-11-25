import { describe, expect, it } from "vitest";

import { ApiError, parseResponse } from "./client";
import { jobSchema, taskDetailSchema, taskListSchema } from "./schemas";

function expectRejected(run: () => unknown, code = "bad_response"): void {
  try {
    run();
    throw new Error("expected a rejection");
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).code).toBe(code);
  }
}

describe("HTTP contracts", () => {
  it("accepts the task list the daemon returns", () => {
    const payload = { ok: true, tasks: [{ id: "t-1", state: "queued", title: "A report" }] };
    expect(parseResponse(taskListSchema, payload, "task list")).toEqual(payload);
  });

  it("rejects a task list whose items have no id", () => {
    expectRejected(() =>
      parseResponse(taskListSchema, { ok: true, tasks: [{ state: "queued" }] }, "task list"),
    );
  });

  it("accepts a detail whose task.source is an object", () => {
    const payload = {
      task: { id: "t-1", state: "proved", source: { kind: "manual", ref: "GH-1" } },
    };
    expect(parseResponse(taskDetailSchema, payload, "task")).toEqual(payload);
  });

  it("rejects a detail payload without a task", () => {
    expectRejected(() => parseResponse(taskDetailSchema, { ok: true }, "task"));
  });

  it("keeps the extra fields of a detail payload", () => {
    const payload = {
      ok: true,
      task: { id: "t-1", state: "proved" },
      pipeline: { blocked: null },
      evidence: { files_changed: [] },
    };
    expect(parseResponse(taskDetailSchema, payload, "task")).toEqual(payload);
  });

  it("rejects an unknown job status", () => {
    expectRejected(() =>
      parseResponse(jobSchema, { id: "j-1", status: "exploded" }, "job"),
    );
  });

  it("names the broken field in the error message", () => {
    try {
      parseResponse(taskListSchema, { tasks: [{}] }, "task list");
    } catch (error) {
      expect((error as ApiError).message).toContain("tasks.0.id");
    }
  });
});
