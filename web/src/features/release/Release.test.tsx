import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Release } from "./Release";
import type { ReleaseDetail, ReleasePacket } from "./Release";
import { provedDetail, releasedDetail } from "../../test/fixtures";

type DraftOverrides = Partial<ReleaseDetail> & {
  release?: Partial<ReleasePacket> | null;
};

function draftDetail(overrides: DraftOverrides = {}) {
  return {
    ...provedDetail,
    release: {
      ...provedDetail.release,
      ready: true,
      released: false,
      blockers: [],
      ...(overrides.release || {}),
    },
    delivery: null,
    confirmation: null,
    deployment: null,
    ...overrides,
  };
}

describe("Release", () => {
  it("shows the released packet and opens runs", () => {
    const onShowRuns = vi.fn();
    const onShowRun = vi.fn();
    const onAction = vi.fn();
    render(
      <Release
        detail={releasedDetail}
        onAction={onAction}
        onShowRuns={onShowRuns}
        onShowRun={onShowRun}
        onToast={vi.fn()}
      />,
    );
    expect(screen.getAllByText("RELEASED").length).toBeGreaterThan(0);
    expect(screen.getByText("Delivery")).toBeInTheDocument();
    expect(screen.getByText("Deployment")).toBeInTheDocument();
    expect(screen.getByText("Confirmation")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(onShowRuns).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open run" }));
    expect(onShowRun).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Verify with team" }));
    expect(onAction).toHaveBeenCalledWith("team-verify");
  });

  it("approves, delivers and confirms as jobs", async () => {
    const onAction = vi.fn(async () => ({}));
    const { unmount } = render(
      <Release
        detail={draftDetail()}
        onAction={onAction}
        onShowRuns={vi.fn()}
        onShowRun={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Approve release" }));
    expect(onAction).toHaveBeenCalledWith("release", { decision: "approved", comment: "" });
    unmount();

    render(
      <Release
        detail={draftDetail({ release: { released: true } })}
        onAction={onAction}
        onShowRuns={vi.fn()}
        onShowRun={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "github" } });
    fireEvent.click(screen.getByRole("button", { name: "Deliver" }));
    await waitFor(() =>
      expect(onAction).toHaveBeenCalledWith(
        "deliver",
        expect.objectContaining({ provider: "github" }),
      ),
    );
  });

  it("shows the risk tier and its reasons at the release gate", () => {
    render(
      <Release
        detail={draftDetail({
          release: {
            risk: "high",
            risk_reasons: ["security-sensitive path: payments/charge.py"],
            risk_files: 2,
            risk_lines: 40,
          },
        })}
        onAction={vi.fn()}
        onShowRuns={vi.fn()}
        onShowRun={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    expect(screen.getByText(/high · 2 file\(s\), 40 line\(s\)/)).toBeInTheDocument();
    expect(screen.getByText("security-sensitive path: payments/charge.py")).toBeInTheDocument();
  });

  it("confirms a delivery with a URL and command", async () => {    const onAction = vi.fn(async () => ({}));
    render(
      <Release
        detail={draftDetail({
          delivery: { commit: "deadbeef", branch: "main", pr_url: null },
          confirmation: null,
        })}
        onAction={onAction}
        onShowRuns={vi.fn()}
        onShowRun={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("URL"), {
      target: { value: "https://example.test/health" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(onAction).toHaveBeenCalledWith(
        "confirm",
        expect.objectContaining({
          url: "https://example.test/health",
          close: false,
        }),
      ),
    );
  });
});


describe("Release summary", () => {
  it("shows the plain-language summary at the gate", () => {
    render(
      <Release
        detail={draftDetail({
          release: {
            summary: "## What was wrong\n\nThe parser drops the last line.\n",
            summary_derived: false,
          },
        })}
        onAction={vi.fn()}
        onShowRuns={vi.fn()}
        onShowRun={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    expect(screen.getByText("Plain-language summary")).toBeInTheDocument();
    expect(screen.getByText("The parser drops the last line.")).toBeInTheDocument();
  });
});
