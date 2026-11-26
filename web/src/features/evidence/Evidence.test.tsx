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


describe("Evidence advisory", () => {
  it("shows the CVE, the package and the fixed release", () => {
    const detail = {
      ...provedDetail,
      evidence: {
        ...provedDetail.evidence,
        advisory: {
          id: "CVE-2026-0001",
          package: "demo-pkg",
          version: "1.2.0",
          severity: "high",
          fixed: "1.4.2",
          cvss: 8.1,
          links: ["https://example.test/advisory"],
        },
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
    expect(screen.getByText("Advisory")).toBeInTheDocument();
    expect(screen.getByText("CVE-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/demo-pkg/)).toBeInTheDocument();
  });
});


describe("Evidence specialist reviews", () => {
  it("shows each specialist and its verdict", () => {
    const detail = {
      ...provedDetail,
      evidence: {
        ...provedDetail.evidence,
        specialists: [
          { area: "security", allow: false, reason: "the token is logged" },
          { area: "performance", allow: true, reason: "no new hot path" },
        ],
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
    expect(screen.getByText("Specialist reviews")).toBeInTheDocument();
    expect(screen.getByText("security")).toBeInTheDocument();
    expect(screen.getByText("the token is logged")).toBeInTheDocument();
  });
});
