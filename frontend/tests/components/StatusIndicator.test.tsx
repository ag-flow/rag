import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusIndicator } from "@/components/StatusIndicator";

describe("StatusIndicator", () => {
  it("renders green dot for present", () => {
    render(<StatusIndicator status="present" />);
    const el = screen.getByRole("status");
    expect(el).toHaveAttribute("aria-label", "secret-present");
    expect(el.className).toContain("bg-emerald-500");
  });

  it("renders orange dot for empty", () => {
    render(<StatusIndicator status="empty" />);
    expect(screen.getByRole("status").className).toContain("bg-amber-500");
  });

  it("renders red dot for missing", () => {
    render(<StatusIndicator status="missing" />);
    expect(screen.getByRole("status").className).toContain("bg-red-500");
  });
});
