import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders } from "./testUtils";
import { WorkerPausedBanner } from "@/pages/workspace/WorkerPausedBanner";
import type { LoadGateStatus } from "@/lib/load-gate";

vi.mock("@/hooks/useLoadGate", () => ({
  useLoadGate: vi.fn(),
}));

import { useLoadGate } from "@/hooks/useLoadGate";

function mockGate(pausedSince: string | null): void {
  const data: LoadGateStatus = {
    enabled: true,
    overloaded: pausedSince !== null,
    cpu_psi_avg60: 1.0,
    memory_used_pct: 85.4,
    memory_source: "meminfo",
    io_psi_avg60: null,
    cpu_threshold_pct: 40,
    memory_threshold_pct: 85,
    io_threshold_pct: 60,
    reasons: pausedSince !== null ? ["memory 85.4 > 85%"] : [],
    worker_paused_since: pausedSince,
  };
  vi.mocked(useLoadGate).mockReturnValue({ data } as unknown as ReturnType<typeof useLoadGate>);
}

const FOUR_DAYS_AGO = new Date(Date.now() - 4 * 86_400_000).toISOString();

describe("WorkerPausedBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  it("signale la pause et sa cause quand des jobs attendent", () => {
    mockGate(FOUR_DAYS_AGO);
    renderWithProviders(<WorkerPausedBanner hasPendingJobs={true} />);
    expect(screen.getByRole("status")).toHaveTextContent("Indexation suspendue");
    expect(screen.getByText(/il y a 4 j \(memory 85\.4 > 85%\)/)).toBeInTheDocument();
  });

  it("reste masqué sans job en attente", () => {
    mockGate(FOUR_DAYS_AGO);
    renderWithProviders(<WorkerPausedBanner hasPendingJobs={false} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reste masqué quand le worker picke", () => {
    mockGate(null);
    renderWithProviders(<WorkerPausedBanner hasPendingJobs={true} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
