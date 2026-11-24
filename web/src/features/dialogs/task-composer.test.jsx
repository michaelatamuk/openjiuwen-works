import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ createTask: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { createTask: mocks.createTask },
}));

import { NewTaskDialog } from "./task-composer.jsx";

const createTask = mocks.createTask;

describe("NewTaskDialog", () => {
  beforeEach(() => {
    createTask.mockReset();
    localStorage.clear();
  });

  it("creates a task from a pasted GitHub issue", async () => {
    createTask.mockResolvedValue({ created: true, task: { id: "t-new" } });
    const onCreated = vi.fn();
    const onToast = vi.fn();
    render(
      <NewTaskDialog
        products={["openjiuwen"]}
        onClose={vi.fn()}
        onCreated={onCreated}
        onToast={onToast}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/What should Mira work on/), {
      target: { value: "https://github.com/acme/widget/issues/7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Use draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Create task" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("t-new"));
    expect(createTask).toHaveBeenCalledWith(
      expect.objectContaining({
        repo: "acme/widget",
        ref: "acme/widget#7",
        product: "openjiuwen",
        kind: "manual",
        task_kind: "fix",
        flow: "fix-issue",
      }),
    );
    expect(onToast).toHaveBeenCalledWith("Created t-new. It is queued.");
    expect(localStorage.getItem("works.repo")).toBe("acme/widget");
  });

  it("reports a duplicate and asks for missing fields", async () => {
    createTask.mockResolvedValue({ created: false, task: { id: "t-old" } });
    const onToast = vi.fn();
    render(
      <NewTaskDialog
        products={["openjiuwen"]}
        onClose={vi.fn()}
        onCreated={vi.fn()}
        onToast={onToast}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Create task" }));
    expect(onToast).toHaveBeenCalledWith("Add a reference and a title under Details.");
    expect(createTask).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText(/What should Mira work on/), {
      target: { value: "Fix acme/widget#9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create task" }));
    await waitFor(() => expect(onToast).toHaveBeenCalledWith("t-old already existed."));
  });
});
