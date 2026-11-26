import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SummaryText } from "./summary";

describe("SummaryText", () => {
  it("keeps a paragraph and the bullets that follow it apart", () => {
    render(
      <SummaryText
        text={"## What changed\n\n1 file(s), 4 line(s) changed.\n- `calc/core.py` (+2, -2)\n- `calc/io.py` (+1, -1)"}
      />,
    );

    expect(screen.getByText("1 file(s), 4 line(s) changed.")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("calc/core.py")).toBeInTheDocument();
  });

  it("renders headings and inline code", () => {
    render(<SummaryText text={"## What proves it\n\nVerdict: `allow`."} />);

    expect(screen.getByRole("heading", { name: "What proves it" })).toBeInTheDocument();
    expect(screen.getByText("allow")).toBeInTheDocument();
  });

  it("says when there is nothing to show", () => {
    render(<SummaryText text={""} />);
    expect(screen.getByText("No summary recorded.")).toBeInTheDocument();
  });
});
