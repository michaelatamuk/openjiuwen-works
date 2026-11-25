import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Story } from "./Story";
import { blockedDetail, provedDetail } from "../../test/fixtures";

describe("Story", () => {
  it("renders the proved story, present mode and copy link", () => {
    const onView = vi.fn();
    const onToast = vi.fn();
    const onShowRun = vi.fn();
    const onAction = vi.fn();
    render(
      <Story
        detail={provedDetail}
        onAction={onAction}
        onView={onView}
        onToast={onToast}
        onShowRun={onShowRun}
      />,
    );

    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
    expect(screen.getByText(/Ready for a person/)).toBeInTheDocument();
    expect(screen.getAllByText(/Release to/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: "Open evidence" })[0]);
    expect(onView).toHaveBeenCalledWith("evidence");

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    expect(onToast).toHaveBeenCalledWith("Link copied.");

    fireEvent.click(screen.getByRole("button", { name: "Present" }));
    expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Present mode" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Present mode" })).not.toBeInTheDocument();
  });

  it("shows the replay controls and the blocked callout", () => {
    const { unmount } = render(
      <Story
        detail={provedDetail}
        onAction={vi.fn()}
        onView={vi.fn()}
        onToast={vi.fn()}
        onShowRun={vi.fn()}
      />,
    );
    if (provedDetail.pipeline?.replay?.length) {
      expect(screen.getByText(/How we got here/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Live" }));
      expect(window.location.hash).toContain("/story");
    }
    unmount();

    render(
      <Story
        detail={blockedDetail}
        onAction={vi.fn()}
        onView={vi.fn()}
        onToast={vi.fn()}
        onShowRun={vi.fn()}
      />,
    );
    expect(screen.getByText("Why it stopped")).toBeInTheDocument();
  });
});


  it("starts a task from the card", () => {
    const onAction = vi.fn();
    const queued = {
      ...provedDetail,
      task: { ...provedDetail.task, state: "queued" },
    };
    render(
      <Story
        detail={queued}
        onAction={onAction}
        onView={vi.fn()}
        onToast={vi.fn()}
        onShowRun={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    expect(onAction).toHaveBeenCalledWith("run");
  });
