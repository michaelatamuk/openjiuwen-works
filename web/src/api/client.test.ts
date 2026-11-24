import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

function reply(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    headers: new Headers({ "content-type": "application/json" }),
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("client", () => {
  it("loads tasks with same-origin credentials", async () => {
    const fetchMock = vi.fn(async () => reply({ tasks: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.tasks()).resolves.toEqual({ tasks: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/tasks?limit=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("turns an error body into ApiError", async () => {
    const fetchMock = vi.fn(async () =>
      reply({ ok: false, error: { code: "auth_error", message: "token required" } }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);

    const error = await api.action({ action: "add-context", task_id: "t-1" }).catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).code).toBe("auth_error");
    expect((error as ApiError).message).toBe("token required");
  });

  it("sends an idempotency key when creating a task", async () => {
    const fetchMock = vi.fn(async () =>
      reply({ ok: true, created: true, task: { id: "t-1" } }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.createTask({ repo: ".", ref: "GH-1", title: "fix" });
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const init = calls[0][1];
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });
});
