import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SchedulerCard } from "./SchedulerCard";

const scheduler = vi.fn();
const pauseScheduler = vi.fn();
const resumeScheduler = vi.fn();
const tickScheduler = vi.fn();
const waitForJob = vi.fn();

vi.mock("../../api/client", () => ({
  api: {
    scheduler: () => scheduler(),
    pauseScheduler: (reason?: string) => pauseScheduler(reason),
    resumeScheduler: () => resumeScheduler(),
    tickScheduler: (limit?: number) => tickScheduler(limit),
  },
  waitForJob: (jobId: string) => waitForJob(jobId),
}));

const status = {
  enabled: true,
  paused: false,
  tick_seconds: 10,
  levels: { default: "L1", by_source: {} },
  limits: { global: 2, per_repo: 1, per_run_usd: 5, remaining_usd: 12.5 },
  active: [],
  eligible: ["t-1"],
  waiting: { "t-2": "repo_busy" },
  counters: {},
};

describe("SchedulerCard", () => {
  beforeEach(() => {
    scheduler.mockReset();
    pauseScheduler.mockReset();
    resumeScheduler.mockReset();
    tickScheduler.mockReset();
    waitForJob.mockReset();
  });

  it("shows the state, budget and waiting reasons", async () => {
    scheduler.mockResolvedValue(status);

    render(<SchedulerCard writable />);

    expect(await screen.findByText(/enabled/)).toBeInTheDocument();
    expect(screen.getByText(/\$12\.50 left today/)).toBeInTheDocument();
    expect(screen.getByText(/t-2: repo_busy/)).toBeInTheDocument();
  });

  it("pauses and resumes", async () => {
    scheduler.mockResolvedValueOnce(status).mockResolvedValue({ ...status, paused: true });
    pauseScheduler.mockResolvedValue({ ok: true, paused: true });
    resumeScheduler.mockResolvedValue({ ok: true, paused: false });

    render(<SchedulerCard writable />);
    await screen.findByText(/enabled/);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));

    await waitFor(() => expect(pauseScheduler).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Resume" })).toBeInTheDocument();
  });

  it("runs one tick as a job", async () => {
    scheduler.mockResolvedValue(status);
    tickScheduler.mockResolvedValue({ ok: true, action: "scheduler.tick", job: { id: "j-1" } });
    waitForJob.mockResolvedValue({ status: "succeeded" });

    render(<SchedulerCard writable />);
    await screen.findByText(/enabled/);

    fireEvent.click(screen.getByRole("button", { name: "Tick now" }));

    await waitFor(() => expect(tickScheduler).toHaveBeenCalledWith(1));
    expect(waitForJob).toHaveBeenCalledWith("j-1");
  });
});
