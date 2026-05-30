import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  baseline_comparison: {
    baseline_run_id: "run-base",
    baseline_model: "ollama/base",
    relative_score: 1.0,
    is_baseline: false,
    computed_at: "2025-01-01T12:00:00Z",
    tasks: [
      {
        task_id: "arithmetic",
        baseline_score: 1.0,
        score: 1.0,
        delta: 0.0,
      },
    ],
  },
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
const setBaseline = vi.hoisted(() => vi.fn());
const clearBaseline = vi.hoisted(() => vi.fn());
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

vi.mock("../hooks/useJobStream", () => ({
  useJobStream: vi.fn((jobId: string | null) => ({
    events: [],
    status: jobId ? "streaming" : "done",
    runId: null,
    comparisonId: null,
    summary: null,
    error: null,
  })),
}));

vi.mock("../api/client", () => ({
  api: {
    getRun,
    getRunJob,
    getBenchmark,
    getTaskOutput,
    setBaseline,
    clearBaseline,
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
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    setBaseline.mockResolvedValue({});
    clearBaseline.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders results and lazy-loads output on expand", async () => {
    getRun.mockResolvedValue(finishedRunDetail);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "run-abc" })).toBeInTheDocument();
    expect(screen.getByText("arithmetic", { selector: ".results-table__task" })).toBeInTheDocument();
    expect(screen.queryByText("4")).not.toBeInTheDocument();

    await user.click(screen.getByText("arithmetic", { selector: ".results-table__task" }));

    await waitFor(() => {
      expect(getTaskOutput).toHaveBeenCalledWith("run-abc", "arithmetic");
    });
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
  });

  it("shows live status and progress for an in-progress run", async () => {
    getRun.mockResolvedValue(liveRunDetail);
    getRunJob.mockResolvedValue({ job_id: "job-live" });
    renderPage("/runs/run-live");

    expect(await screen.findByRole("heading", { name: "run-live" })).toBeInTheDocument();
    expect(await screen.findByText("Live")).toBeInTheDocument();
    expect(await screen.findByText("1 / 1 tasks")).toBeInTheDocument();
    expect(getRunJob).toHaveBeenCalled();
    expect(getBenchmark).toHaveBeenCalled();
  });

  it("renders baseline comparison table with delta", async () => {
    getRun.mockResolvedValue(finishedRunDetail);
    renderPage();

    const section = (await screen.findByText("Baseline comparison")).closest("section");
    expect(section).not.toBeNull();
    const scope = within(section!);
    expect(scope.getByRole("link", { name: "run-base" })).toBeInTheDocument();
    expect(scope.getByText("1.00×")).toBeInTheDocument();
    expect(scope.getByText("0.00")).toBeInTheDocument();
  });

  it("shows baseline note when run is the baseline", async () => {
    getRun.mockResolvedValue({
      ...finishedRunDetail,
      baseline_comparison: {
        ...finishedRunDetail.baseline_comparison!,
        is_baseline: true,
        tasks: [],
      },
    });
    renderPage();

    expect(await screen.findByText("This run is the baseline.")).toBeInTheDocument();
  });

  it("calls setBaseline when empty star clicked", async () => {
    getRun.mockResolvedValue({
      ...finishedRunDetail,
      baseline_comparison: {
        ...finishedRunDetail.baseline_comparison!,
        is_baseline: false,
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Set run-abc as baseline" }),
    );
    expect(setBaseline).toHaveBeenCalledWith("run-abc", expect.anything());
  });

  it("calls clearBaseline when filled star clicked", async () => {
    getRun.mockResolvedValue({
      ...finishedRunDetail,
      baseline_comparison: {
        ...finishedRunDetail.baseline_comparison!,
        is_baseline: true,
        tasks: [],
      },
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Clear baseline for run-abc" }),
    );
    expect(clearBaseline).toHaveBeenCalledWith("run-abc", expect.anything());
  });

  it("stops polling and shows interrupted when no active job exists", async () => {
    getRun.mockResolvedValue({
      ...liveRunDetail,
      results: [],
    });
    getRunJob.mockResolvedValue(null);
    renderPage("/runs/run-live");

    expect(await screen.findByRole("heading", { name: "run-live" })).toBeInTheDocument();
    expect(await screen.findByText("Interrupted", {}, { timeout: 8000 })).toBeInTheDocument();

    const callsAfterStop = getRunJob.mock.calls.length;
    expect(callsAfterStop).toBeGreaterThanOrEqual(3);
    await new Promise((resolve) => setTimeout(resolve, 3000));
    expect(getRunJob.mock.calls.length).toBe(callsAfterStop);
  }, 15_000);
});
