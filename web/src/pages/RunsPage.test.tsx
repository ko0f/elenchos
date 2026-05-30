import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunsPage } from "./RunsPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const runs = [
  {
    run_id: "run-a",
    started_at: "2025-01-01T00:00:00Z",
    model: "ollama/a",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 1.0 },
    is_baseline: true,
    baseline_score: 1.0,
    baseline_run_id: "run-a",
  },
  {
    run_id: "run-b",
    started_at: "2025-01-01T01:00:00Z",
    model: "ollama/b",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 0.5 },
    is_baseline: false,
    baseline_score: 0.5,
    baseline_run_id: "run-a",
  },
  {
    run_id: "run-c",
    started_at: "2025-01-01T02:00:00Z",
    model: "ollama/c",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 0.75 },
    is_baseline: false,
    baseline_score: 0.75,
    baseline_run_id: "run-a",
  },
];

const { listRuns, listComparisons, deleteRun } = vi.hoisted(() => ({
  listRuns: vi.fn(),
  listComparisons: vi.fn(),
  deleteRun: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: {
    listRuns,
    listComparisons,
    deleteRun,
  },
  queryKeys: {
    runs: ["runs"],
    comparisons: ["comparisons"],
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RunsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RunsPage", () => {
  beforeEach(() => {
    cleanup();
    listRuns.mockClear();
    listComparisons.mockClear();
    deleteRun.mockClear();
    listRuns.mockResolvedValue(runs);
    listComparisons.mockResolvedValue([]);
    mockNavigate.mockClear();
    vi.stubGlobal("confirm", () => true);
  });

  afterEach(() => {
    cleanup();
  });

  it("enables compare only for two same-benchmark runs", async () => {
    const user = userEvent.setup();
    renderPage();

    const compare = await screen.findByRole("button", { name: "Compare selected" });
    expect(compare).toBeDisabled();

    expect(screen.queryByLabelText("Select run-a")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Select run-b"));
    expect(compare).toBeDisabled();

    await user.click(screen.getByLabelText("Select run-c"));
    expect(compare).toBeEnabled();

    await user.click(compare);
    expect(mockNavigate).toHaveBeenCalledWith("/compare?runs=run-b,run-c");
  });

  it("deletes a run after confirmation", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Delete run-a" }));
    expect(deleteRun).toHaveBeenCalledWith("run-a", expect.anything());
  });

  it("does not delete when confirmation is cancelled", async () => {
    vi.stubGlobal("confirm", () => false);
    const user = userEvent.setup();
    renderPage();

    const [deleteButton] = await screen.findAllByRole("button", { name: "Delete run-a" });
    await user.click(deleteButton);
    expect(deleteRun).not.toHaveBeenCalled();
  });

  it("renders baseline badge and relative score", async () => {
    renderPage();

    expect(await screen.findByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("0.50×")).toBeInTheDocument();
  });

  it("navigates to run detail when row clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("row", {
        name: "View run: ollama/a, text-reasoning-v1",
      }),
    );
    expect(mockNavigate).toHaveBeenCalledWith("/runs/run-a");
  });

  it("does not navigate when checkbox clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByLabelText("Select run-b"));
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("renders comparisons table below runs", async () => {
    listComparisons.mockResolvedValue([
      {
        comparison_id: "cmp-1",
        mode: "pairwise",
        judge_model: "ollama/judge",
        benchmark_id: "text-reasoning-v1",
        started_at: "2025-01-02T00:00:00Z",
        run_ids: ["run-a", "run-b"],
      },
    ]);
    renderPage();

    expect(await screen.findByRole("table", { name: "Comparisons" })).toBeInTheDocument();
    expect(screen.getByText("cmp-1")).toBeInTheDocument();
    expect(screen.getByText("pairwise")).toBeInTheDocument();
  });
});
