import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import { isActiveStatus, isTerminalStatus, useEvents, useTasks } from "./hooks";

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("hooks", () => {
  it("classifies job statuses", () => {
    expect(isActiveStatus("queued")).toBe(true);
    expect(isActiveStatus("running")).toBe(true);
    expect(isTerminalStatus("succeeded")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
    expect(isTerminalStatus("cancelled")).toBe(true);
  });

  it("loads the task list through the query client", async () => {
    vi.spyOn(api, "tasks").mockResolvedValue({ tasks: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useTasks(), { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ tasks: [] });
  });

  it("invalidates the right caches for named events", () => {
    class FakeSource {
      static latest: FakeSource | null = null;
      readonly listeners = new Map<string, (event: MessageEvent) => void>();
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public url: string) {
        FakeSource.latest = this;
      }
      addEventListener(name: string, handler: (event: MessageEvent) => void) {
        this.listeners.set(name, handler);
      }
      close() {
        this.listeners.clear();
      }
      emit(name: string, data: unknown) {
        this.listeners.get(name)?.({ data: JSON.stringify(data) } as MessageEvent);
      }
    }
    vi.stubGlobal("EventSource", FakeSource);

    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useEvents(), { wrapper: wrapperFor(client) });

    FakeSource.latest?.emit("task.changed", { task_id: "t-1" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["tasks"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["task", "t-1"] });
  });
});
