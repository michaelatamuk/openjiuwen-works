import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsDialog } from "./SettingsDialog.jsx";
import { builderHealth } from "../../test/fixtures";

describe("SettingsDialog", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("saves the workspace and builder settings", async () => {
    const onSave = vi.fn(async () => ({}));
    render(
      <SettingsDialog
        theme="dark"
        density="comfortable"
        pollMs={5000}
        builder={builderHealth}
        writable
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Local / writable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());

    const payload = onSave.mock.calls[0][0];
    expect(payload).toMatchObject({
      theme: "dark",
      density: "comfortable",
      pollMs: 5000,
      repo: "",
    });
    expect(payload.builder).toMatchObject({
      runtime: "openjiuwen",
      provider: "claudecode",
      planner_mode: "deterministic",
      planner_provider: null,
      planner_model: null,
    });
  });

  it("marks the read-only mode and reports a save failure", async () => {
    const onSave = vi.fn(async () => {
      throw new Error("read only");
    });
    render(
      <SettingsDialog
        theme="light"
        density="compact"
        pollMs={5000}
        builder={builderHealth}
        writable={false}
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("read only")).toBeInTheDocument());
  });
});
