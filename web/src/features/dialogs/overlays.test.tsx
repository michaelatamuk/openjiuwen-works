import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HelpDialog, Palette } from "./palette";
import { EventDialog, Lightbox } from "./overlays";
import { CompareDialog, RunDialog } from "./run";
import { provedDetail, taskRow } from "../../test/fixtures";

describe("dialogs and overlays", () => {
  it("opens run and compare dialogs", () => {
    const closeRun = vi.fn();
    const { unmount } = render(<RunDialog detail={provedDetail} onClose={closeRun} />);
    expect(screen.getByRole("heading", { name: "Run" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closeRun).toHaveBeenCalled();
    unmount();

    const closeCompare = vi.fn();
    render(<CompareDialog detail={provedDetail} onClose={closeCompare} />);
    expect(screen.getByRole("heading", { name: "Compare runs" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closeCompare).toHaveBeenCalled();
  });

  it("shows the event payload, artifact lightbox and keyboard help", () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EventDialog event={{ type: "state.changed", data: { to: "proved" } }} onClose={onClose} />,
    );
    expect(screen.getByRole("heading", { name: "Event" })).toBeInTheDocument();
    expect(screen.getByText(/state.changed/)).toBeInTheDocument();
    unmount();

    const closeImage = vi.fn();
    const lightbox = render(
      <Lightbox
        image={{ url: "/api/v1/tasks/t-1/artifacts/shot.png", alt: "after the fix" }}
        onClose={closeImage}
      />,
    );
    expect(screen.getByAltText("after the fix")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closeImage).toHaveBeenCalled();
    lightbox.unmount();

    const closeHelp = vi.fn();
    render(<HelpDialog onClose={closeHelp} />);
    expect(screen.getByRole("heading", { name: "Keyboard" })).toBeInTheDocument();
    expect(screen.getByText("Ctrl K")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closeHelp).toHaveBeenCalled();
  });

  it("filters palette actions and selects a task", () => {
    const onAction = vi.fn();
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(
      <Palette
        tasks={[taskRow({ id: "t-9", title: "Fix the queue", product: "Fixture" })]}
        onSelect={onSelect}
        onAction={onAction}
        onClose={onClose}
        writable
      />,
    );
    expect(screen.getByRole("button", { name: "New task" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(onAction).toHaveBeenCalledWith("settings");

    fireEvent.change(screen.getByLabelText("Command palette search"), {
      target: { value: "queue" },
    });
    expect(screen.queryByRole("button", { name: "Settings" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Fix the queue/ }));
    expect(onSelect).toHaveBeenCalledWith("t-9");
    expect(onClose).toHaveBeenCalled();
  });

  it("hides write-only palette actions in read-only mode", () => {
    render(
      <Palette
        tasks={[]}
        onSelect={vi.fn()}
        onAction={vi.fn()}
        onClose={vi.fn()}
        writable={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "New task" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import signals" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Factory metrics" })).toBeInTheDocument();
  });
});
