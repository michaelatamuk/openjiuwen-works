import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Evidence } from "./Evidence.jsx";
import { provedDetail } from "../../test/fixtures";

describe("Evidence", () => {
  it("shows the proof cards and versioned export links", () => {
    const onAction = vi.fn();
    const onShowRun = vi.fn();
    render(
      <Evidence
        detail={provedDetail}
        onShowRun={onShowRun}
        onAction={onAction}
        onLightbox={vi.fn()}
        onOpenEvent={vi.fn()}
        onToast={vi.fn()}
      />,
    );

    for (const title of [
      "Run metadata",
      "Policy",
      "Risk",
      "Decision",
      "Cost",
      "Verifier",
      "Verification team",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }

    const taskId = provedDetail.task.id;
    expect(
      screen.getByRole("link", { name: "proof.md" }),
    ).toHaveAttribute("href", `/api/v1/tasks/${encodeURIComponent(taskId)}/export/evidence.md`);
    expect(screen.getByRole("link", { name: "evidence.json" })).toHaveAttribute(
      "href",
      `/api/v1/tasks/${encodeURIComponent(taskId)}/export/evidence.json`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open run" }));
    expect(onShowRun).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Verify with team" }));
    expect(onAction).toHaveBeenCalledWith("team-verify");
  });

  it("runs readiness and renders runtime artifacts", () => {
    const onAction = vi.fn();
    render(
      <Evidence
        detail={provedDetail}
        onShowRun={vi.fn()}
        onAction={onAction}
        onLightbox={vi.fn()}
        onOpenEvent={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    if (provedDetail.readiness) {
      expect(screen.getByText("Readiness")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Run checks" }));
      expect(onAction).toHaveBeenCalledWith("run-readiness");
    }
    if (provedDetail.artifacts?.length) {
      expect(screen.getByText("Runtime artifacts")).toBeInTheDocument();
      expect(screen.getByText("screenshot.txt")).toBeInTheDocument();
    }
  });
});
