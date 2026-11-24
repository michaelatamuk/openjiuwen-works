import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ metrics: vi.fn(), ledger: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { metrics: mocks.metrics, ledger: mocks.ledger },
}));

import { FactoryDialog } from "./factory.jsx";

const metrics = mocks.metrics;
const ledger = mocks.ledger;

describe("FactoryDialog", () => {
  beforeEach(() => {
    metrics.mockReset();
    ledger.mockReset();
    metrics.mockResolvedValue({
      metrics: {
        tasks: 12,
        proved: 9,
        blocked: 1,
        human_touches: 2,
        runs_without_human: 7,
        median_duration_ms: 45000,
        tokens: 1234,
        usd: 0.56,
      },
    });
    ledger.mockResolvedValue({
      rows: [
        {
          ts: "2026-11-21T09:00:00Z",
          task_id: "t-1",
          state: "proved",
          verdict: "allow",
          tokens: 10,
          usd: 0.01,
        },
      ],
    });
  });

  it("loads metrics and the ledger, then closes", async () => {
    const onClose = vi.fn();
    render(<FactoryDialog onClose={onClose} />);

    expect(screen.getByText("Loading factory metrics…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Tasks")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("t-1")).toBeInTheDocument();
    expect(screen.getByText("allow")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("reports a metrics failure", async () => {
    metrics.mockRejectedValue(new Error("daemon offline"));
    render(<FactoryDialog onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("daemon offline")).toBeInTheDocument());
  });
});
