import type { ComponentProps } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunTableProgressCell } from "./RunTableProgressCell";

const getRunJob = vi.hoisted(() => vi.fn());
const getBenchmark = vi.hoisted(() => vi.fn());
const getJob = vi.hoisted(() => vi.fn());

vi.mock("../api/client", () => ({
  api: {
    getRunJob,
    getBenchmark,
    getJob,
  },
  queryKeys: {
    runs: ["runs"],
    run: (id: string) => ["runs", id],
    runJob: (id: string) => ["runs", id, "job"],
    benchmark: (id: string) => ["benchmarks", id],
  },
}));

vi.mock("../hooks/useJobStream", () => ({
  useJobStream: (jobId: string | null) => ({
    events:
      jobId == null
        ? []
        : [
            { event: "task_done", data: { task_id: "t1", index: 0, total: 4 } },
            { event: "task_done", data: { task_id: "t2", index: 1, total: 4 } },
          ],
    status: jobId ? "streaming" : "done",
    runId: "run-live",
    comparisonId: null,
    summary: null,
    error: null,
  }),
}));

function renderCell(props: Partial<ComponentProps<typeof RunTableProgressCell>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <RunTableProgressCell
        runId="run-live"
        finishedAt={null}
        benchmarkId="text-reasoning-v1"
        baselineScore={null}
        isBaseline={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("RunTableProgressCell", () => {
  beforeEach(() => {
    cleanup();
    getRunJob.mockReset();
    getBenchmark.mockReset();
    getJob.mockReset();
    getRunJob.mockResolvedValue({ job_id: "job-live" });
    getBenchmark.mockResolvedValue({ tasks: [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }] });
  });

  afterEach(() => {
    cleanup();
  });

  it("shows baseline badge for finished runs", () => {
    renderCell({
      finishedAt: "2025-01-01T01:00:00Z",
      baselineScore: 0.75,
    });

    expect(screen.getByText("0.75×")).toBeInTheDocument();
  });

  it("shows task progress for live runs", async () => {
    renderCell();

    expect(await screen.findByText("2/4")).toBeInTheDocument();
  });
});
