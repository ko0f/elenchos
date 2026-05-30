import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RunDetailPage } from "./RunDetailPage";

const runDetail = {
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

const getTaskOutput = vi.fn(async () => "4");

vi.mock("../api/client", () => ({
  api: {
    getRun: vi.fn(async () => runDetail),
    getTaskOutput,
  },
  queryKeys: {
    run: (id: string) => ["runs", id],
    taskOutput: (runId: string, taskId: string) => ["runs", runId, "output", taskId],
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/runs/run-abc"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RunDetailPage", () => {
  it("renders results and lazy-loads output on expand", async () => {
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
});
