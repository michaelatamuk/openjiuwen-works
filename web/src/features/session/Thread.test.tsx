import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ action: vi.fn(), askStream: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { action: mocks.action },
  askStream: mocks.askStream,
}));

import { Thread } from "./Thread";
import type { ThreadProps } from "./Thread";
import type { Json } from "../../api/client";
import { provedDetail } from "../../test/fixtures";

const action = mocks.action;
const askStream = mocks.askStream;

function renderThread(overrides: Partial<ThreadProps> = {}) {
  return render(
    <Thread
      detail={provedDetail}
      ai={{ available: true }}
      writable
      onAction={vi.fn()}
      onView={vi.fn()}
      onRefresh={vi.fn()}
      onShowRun={vi.fn()}
      onToast={vi.fn()}
      {...overrides}
    />,
  );
}

describe("Thread", () => {
  beforeEach(() => {
    action.mockReset();
    askStream.mockReset();
  });

  it("streams a question through ask", async () => {
    askStream.mockImplementation(
      async (_id: string, _question: string, onEvent: (event: Json) => void) => {
        onEvent({ type: "delta", text: "checking" });
        return null;
      },
    );
    const onRefresh = vi.fn();
    renderThread({ onRefresh });

    const input = screen.getByPlaceholderText("Ask about this run...");
    fireEvent.change(input, { target: { value: "What changed?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Mira" }));

    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    expect(askStream).toHaveBeenCalledWith(
      provedDetail.task.id,
      "What changed?",
      expect.any(Function),
    );
  });

  it("adds context when the mode is a note", async () => {
    action.mockResolvedValue({ ok: true });
    const onRefresh = vi.fn();
    const onToast = vi.fn();
    renderThread({ onRefresh, onToast });

    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const input = screen.getByPlaceholderText("Add context to this run...");
    fireEvent.change(input, { target: { value: "The flake is timing." } });
    fireEvent.click(screen.getByRole("button", { name: "Add context" }));

    await waitFor(() =>
      expect(action).toHaveBeenCalledWith({
        action: "add-context",
        task_id: provedDetail.task.id,
        message: "The flake is timing.",
      }),
    );
    expect(onToast).toHaveBeenCalledWith("Context added to the worklog.");
    expect(onRefresh).toHaveBeenCalled();
  });

  it("falls back to notes when the assistant is unavailable", () => {
    renderThread({ ai: { available: false } });
    expect(screen.getAllByText("Note").length).toBeGreaterThan(0);
    expect(screen.getByPlaceholderText("Add context to this run...")).toBeInTheDocument();
  });
});
