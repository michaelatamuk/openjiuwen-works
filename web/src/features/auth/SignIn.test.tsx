import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ connect: vi.fn() }));

vi.mock("../../api/client", () => ({ connect: mocks.connect }));

import { SignIn } from "./SignIn";

describe("SignIn", () => {
  beforeEach(() => {
    mocks.connect.mockReset();
  });

  it("exchanges the credential and reloads the workspace", async () => {
    mocks.connect.mockResolvedValue(undefined);
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);

    fireEvent.change(screen.getByLabelText("Token or pairing code"), {
      target: { value: "  secret-token  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(onSignedIn).toHaveBeenCalledTimes(1));
    expect(mocks.connect).toHaveBeenCalledWith("  secret-token  ");
  });

  it("shows the daemon error and stays on the screen", async () => {
    mocks.connect.mockRejectedValue(new Error("That is not a valid token or pairing code"));
    const onSignedIn = vi.fn();
    render(<SignIn onSignedIn={onSignedIn} />);

    fireEvent.change(screen.getByLabelText("Token or pairing code"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("not a valid token"),
    );
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("keeps the button disabled until a credential is typed", () => {
    render(<SignIn onSignedIn={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
  });
});
