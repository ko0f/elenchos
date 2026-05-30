import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LeaderboardPage } from "./LeaderboardPage";

const runs = [
  {
    run_id: "run-a",
    started_at: "2025-01-01T00:00:00Z",
    model: "ollama/a",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 1.0 },
  },
  {
    run_id: "run-b",
    started_at: "2025-01-01T01:00:00Z",
    model: "ollama/b",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 0.5 },
  },
];

const buildReport = vi.hoisted(() =>
  vi.fn(async () => ({
    benchmark_id: "text-reasoning-v1",
    runs: [
      {
        run_id: "run-a",
        model: "ollama/a",
        benchmark_id: "text-reasoning-v1",
        mean_score: 1.0,
        pass_rate: 1.0,
        p95_latency_ms: 100,
        task_count: 2,
        rank: 1,
        win_rate: null,
      },
      {
        run_id: "run-b",
        model: "ollama/b",
        benchmark_id: "text-reasoning-v1",
        mean_score: 0.5,
        pass_rate: 0.5,
        p95_latency_ms: 120,
        task_count: 2,
        rank: 2,
        win_rate: null,
      },
    ],
  })),
);

vi.mock("../api/client", () => ({
  api: {
    listRuns: vi.fn(async () => runs),
    buildReport,
  },
  queryKeys: {
    runs: ["runs"],
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeaderboardPage />
    </QueryClientProvider>,
  );
}

describe("LeaderboardPage", () => {
  it("renders leaderboard rows after generation", async () => {
    const user = userEvent.setup();
    renderPage();

    const generate = await screen.findByRole("button", { name: "Generate leaderboard" });
    expect(generate).toBeDisabled();

    await user.click(screen.getByLabelText("Select run-a"));
    await user.click(screen.getByLabelText("Select run-b"));
    expect(generate).toBeEnabled();

    await user.click(generate);

    await waitFor(() => {
      expect(buildReport).toHaveBeenCalledWith({
        run_ids: ["run-a", "run-b"],
        format: "json",
      });
    });

    const leaderboard = await screen.findByRole("table", { name: "Leaderboard results" });
    expect(leaderboard).toHaveTextContent("ollama/a");
    expect(leaderboard).toHaveTextContent("run-a");
    expect(leaderboard).toHaveTextContent("1.00");
  });
});
