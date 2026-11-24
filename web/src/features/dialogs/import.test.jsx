import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sources: vi.fn(), waitForJob: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { sources: mocks.sources },
  waitForJob: mocks.waitForJob,
}));

import { ImportDialog } from "./import.jsx";

const sources = mocks.sources;
const waitForJob = mocks.waitForJob;

describe("ImportDialog", () => {
  beforeEach(() => {
    sources.mockReset();
    waitForJob.mockReset();
    localStorage.clear();
    sources.mockResolvedValue({ job: { id: "j-import" } });
    waitForJob.mockResolvedValue({
      status: "succeeded",
      result: { created: 2, duplicates: 1 },
    });
  });

  it("imports GitHub issues and reports the job counts", async () => {
    const onImported = vi.fn();
    const onToast = vi.fn();
    render(
      <ImportDialog
        products={["openjiuwen"]}
        detectors={[{ name: "errors", product: "Fixture" }]}
        onClose={vi.fn()}
        onImported={onImported}
        onToast={onToast}
      />,
    );

    fireEvent.change(screen.getByLabelText("Repository"), {
      target: { value: "acme/widget" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(onToast).toHaveBeenCalledWith("2 task(s) imported."));
    expect(sources).toHaveBeenCalledWith({
      source: "github",
      product: "openjiuwen",
      repo: "",
      repository: "acme/widget",
      label: "bug",
    });
    expect(waitForJob).toHaveBeenCalledWith("j-import");
    expect(onImported).toHaveBeenCalled();
  });

  it("surfaces a failed import as a toast", async () => {
    waitForJob.mockResolvedValue({ status: "failed", error: "tracker unavailable" });
    const onToast = vi.fn();
    render(
      <ImportDialog
        products={["openjiuwen"]}
        detectors={[]}
        onClose={vi.fn()}
        onImported={vi.fn()}
        onToast={onToast}
      />,
    );
    fireEvent.change(screen.getByLabelText("Repository"), {
      target: { value: "acme/widget" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(onToast).toHaveBeenCalledWith("Import failed: tracker unavailable"),
    );
  });
});
