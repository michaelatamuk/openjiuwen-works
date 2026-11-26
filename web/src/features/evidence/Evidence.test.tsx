import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Evidence } from "./Evidence";
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


describe("Evidence summary", () => {
  it("opens on the plain-language summary and switches to technical", () => {
    const detail = {
      ...provedDetail,
      proof_summary: {
        text: "## What was wrong\n\nThe parser drops the last line.\n\n## What proves it\n\nVerdict: allow.",
        sha256: "a".repeat(64),
        derived: false,
      },
    };
    render(
      <Evidence
        detail={detail}
        onShowRun={vi.fn()}
        onAction={vi.fn()}
        onLightbox={vi.fn()}
        onOpenEvent={vi.fn()}
        onToast={vi.fn()}
      />,
    );
    expect(screen.getByText("Run metadata")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Summary" }));
    expect(screen.getByText("The parser drops the last line.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Technical" }));
    expect(screen.getByText("Run metadata")).toBeInTheDocument();
  });
});
