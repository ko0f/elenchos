import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RunDetailPage } from "./RunDetailPage";

const finishedRunDetail = {
  run: {
    run_id: "run-abc",
    started_at: "2025-01-01T12:00:00Z",
    finished_at: "2025-01-01T12:01:00Z",
    model: "ollama/llama3.1:8b",
    params: { temperature: 0.0 },
    tool_version: "0.1.0",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 1.0, pass_rate: 1.0, p95_latency_ms: 150.0 },
  },
  results: [
    {
      task_id: "arithmetic",
      latency_ms: 150.0,
      prompt: "What is 2+2?",
      score: 1.0,
      scorer: "exact_match",
      finish_reason: "stop",
    },
  ],
};

const liveRunDetail = {
  run: {
    run_id: "run-live",
    started_at: "2025-01-01T12:00:00Z",
    finished_at: null,
    model: "ollama/llama3.1:8b",
    params: { temperature: 0.0 },
    tool_version: "0.1.0",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: null,
  },
  results: [
    {
      task_id: "arithmetic",
      latency_ms: 150.0,
      score: 1.0,
    },
  ],
};

const getRun = vi.hoisted(() => vi.fn(async () => finishedRunDetail));
const getRunJob = vi.hoisted(() => vi.fn(async () => null as { job_id: string } | null));
const getTaskOutput = vi.hoisted(() => vi.fn(async () => "4"));
const getBenchmark = vi.hoisted(() =>
  vi.fn(async () => ({
    id: "text-reasoning-v1",
    version: 1,
    type: "text",
    description: "",
    tasks: [{ id: "arithmetic", description: "", type: "text", prompt: "x", scorers: [] }],
    requires_code_exec: false,
    requires_judge: false,
  })),
);

vi.mock("../api/client", () => ({
  api: {
    getRun,
    getRunJob,
    getBenchmark,
    getTaskOutput,
  },
  queryKeys: {
    run: (id: string) => ["runs", id],
    runJob: (id: string) => ["runs", id, "job"],
    benchmark: (id: string) => ["benchmarks", id],
    runs: ["runs"],
    taskOutput: (runId: string, taskId: string) => ["runs", runId, "output", taskId],
  },
}));

function renderPage(path = "/runs/run-abc") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RunDetailPage", () => {
  it("renders results and lazy-loads output on expand", async () => {
    getRun.mockResolvedValue(finishedRunDetail);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "run-abc" })).toBeInTheDocument();
    expect(screen.getByText("arithmetic")).toBeInTheDocument();
    expect(screen.queryByText("4")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show" }));

    await waitFor(() => {
      expect(getTaskOutput).toHaveBeenCalledWith("run-abc", "arithmetic");
    });
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
  });

  it("shows live status and progress for an in-progress run", async () => {
    getRun.mockResolvedValue(liveRunDetail);
    getRunJob.mockResolvedValue(null);
    renderPage("/runs/run-live");

    expect(await screen.findByRole("heading", { name: "run-live" })).toBeInTheDocument();
    expect(await screen.findByText("Live")).toBeInTheDocument();
    expect(await screen.findByText("1 / 1 tasks")).toBeInTheDocument();
    expect(getRunJob).toHaveBeenCalled();
    expect(getBenchmark).toHaveBeenCalled();
  });
});
