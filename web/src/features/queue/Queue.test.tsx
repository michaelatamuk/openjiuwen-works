import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Queue } from "./Queue";
import type { QueueProps } from "./Queue";
import { taskRow } from "../../test/fixtures";

function renderQueue(overrides: Partial<QueueProps> = {}) {
  const props = {
    tasks: [
      taskRow({ id: "t-1", state: "queued", title: "Queued bug", product: "Alpha" }),
      taskRow({
        id: "t-2",
        state: "proved",
        title: "Proved fix",
        product: "Beta",
        source: "tracker:JIRA-2",
        risk: "medium",
      }),
      taskRow({
        id: "t-3",
        state: "blocked",
        title: "Blocked issue",
        product: "Alpha",
        source: "detector:monitor",
      }),
    ],
    selected: "t-1",
    onSelect: vi.fn(),
    filter: "all",
    onFilter: vi.fn(),
    productFilter: "",
    onProductFilter: vi.fn(),
    sourceFilter: "",
    onSourceFilter: vi.fn(),
    query: "",
    onQuery: vi.fn(),
    writable: true,
    inbox: null,
    onMerge: vi.fn(),
    onNew: vi.fn(),
    ...overrides,
  };
  render(<Queue {...props} />);
  return props;
}

describe("Queue", () => {
  it("groups tasks and keeps the selected row marked", () => {
    renderQueue();
    expect(screen.getByRole("complementary", { name: "Queue" })).toBeInTheDocument();
    expect(document.querySelector(".group-label")?.textContent).toContain("Needs you");
    expect(
      [...document.querySelectorAll(".group-label")].some((label) =>
        label.textContent?.includes("Queued"),
      ),
    ).toBe(true);
    expect(screen.getByRole("button", { name: /Proved fix/ })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("button", { name: /Queued bug/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("filters by group and exposes the active filter", () => {
    const props = renderQueue();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(props.onFilter).toHaveBeenCalledWith("done");

    cleanup();
    renderQueue({ filter: "done" });
    expect(screen.getByText("No tasks match.")).toBeInTheDocument();
  });

  it("filters by product, source and free text", () => {
    const props = renderQueue();
    fireEvent.change(screen.getByLabelText("Filter by product"), {
      target: { value: "Alpha" },
    });
    expect(props.onProductFilter).toHaveBeenCalledWith("Alpha");

    fireEvent.change(screen.getByLabelText("Filter by source"), {
      target: { value: "tracker" },
    });
    expect(props.onSourceFilter).toHaveBeenCalledWith("tracker");

    fireEvent.change(screen.getByLabelText("Search tasks"), {
      target: { value: "blocked" },
    });
    expect(props.onQuery).toHaveBeenCalledWith("blocked");

    cleanup();
    renderQueue({ query: "beta" });
    expect(screen.getByRole("button", { name: /Proved fix/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Queued bug/ })).not.toBeInTheDocument();
  });

  it("selects a row and creates a task only in write mode", () => {
    const props = renderQueue();
    fireEvent.click(screen.getByRole("button", { name: /Proved fix/ }));
    expect(props.onSelect).toHaveBeenCalledWith("t-2");
    fireEvent.click(screen.getByRole("button", { name: "+ New task" }));
    expect(props.onNew).toHaveBeenCalled();

    cleanup();
    renderQueue({ writable: false });
    expect(screen.queryByRole("button", { name: "+ New task" })).not.toBeInTheDocument();
    expect(screen.getByText("Local / read-only")).toBeInTheDocument();
  });
});
