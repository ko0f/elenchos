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
];

const { listRuns, deleteRun } = vi.hoisted(() => ({
  listRuns: vi.fn(),
  deleteRun: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: {
    listRuns,
    deleteRun,
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
    deleteRun.mockClear();
    listRuns.mockResolvedValue(runs);
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

    await user.click(screen.getByLabelText("Select run-a"));
    expect(compare).toBeDisabled();

    await user.click(screen.getByLabelText("Select run-b"));
    expect(compare).toBeEnabled();

    await user.click(compare);
    expect(mockNavigate).toHaveBeenCalledWith("/compare?runs=run-a,run-b");
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

    await user.click(await screen.findByLabelText("Select run-a"));
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
