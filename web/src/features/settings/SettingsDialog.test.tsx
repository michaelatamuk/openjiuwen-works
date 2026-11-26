import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  devices: vi.fn(),
  pairStart: vi.fn(),
  revokeDevice: vi.fn(),
  scheduler: vi.fn(),
  waitForJob: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  api: {
    devices: mocks.devices,
    pairStart: mocks.pairStart,
    revokeDevice: mocks.revokeDevice,
    scheduler: mocks.scheduler,
  },
  waitForJob: mocks.waitForJob,
}));

import { SettingsDialog } from "./SettingsDialog";
import type { SettingsSavePayload } from "./types";
import { builderHealth } from "../../test/fixtures";

describe("SettingsDialog", () => {
  beforeEach(() => {
    localStorage.clear();
    mocks.devices.mockReset();
    mocks.pairStart.mockReset();
    mocks.revokeDevice.mockReset();
    mocks.devices.mockResolvedValue({ devices: [] });
    mocks.scheduler.mockResolvedValue({
      enabled: false,
      paused: false,
      tick_seconds: 10,
      levels: { default: "L1", by_source: {} },
      limits: { global: 2, per_repo: 1, per_run_usd: 5, remaining_usd: null },
      active: [],
      eligible: [],
      waiting: {},
      counters: {},
    });
    mocks.pairStart.mockResolvedValue({
      ok: true,
      code: "PAIR-123",
      label: "device",
      expires_in: 300,
    });
    mocks.revokeDevice.mockResolvedValue({ ok: true, revoked: true });
  });

  it("saves the workspace and builder settings", async () => {
    const onSave = vi.fn(async (_payload: SettingsSavePayload) => ({}));
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


  it("lists, pairs and revokes devices", async () => {
    mocks.devices.mockResolvedValueOnce({
      devices: [
        { id: "dev-1", label: "phone", created_at: 1, last_seen: 1, expires_at: 2 },
      ],
    });
    render(
      <SettingsDialog
        theme="light"
        density="compact"
        pollMs={5000}
        builder={builderHealth}
        writable
        onSave={vi.fn(async () => ({}))}
        onClose={vi.fn()}
      />,
    );
    expect(await screen.findByText("phone")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pair a phone" }));
    expect(await screen.findByText("PAIR-123")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(mocks.revokeDevice).toHaveBeenCalledWith("dev-1"));
  });
