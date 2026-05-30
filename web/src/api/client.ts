import type {
  ComparisonDetail,
  ComparisonSummary,
  CreateCompareRequest,
  CreateCompareResponse,
  CreateRunRequest,
  CreateRunResponse,
  JobStatus,
  LeaderboardReport,
  ModelsResponse,
  PromptRequest,
  PromptResponse,
  Provider,
  ReportRequest,
  RunDetail,
  RunJob,
  RunSummary,
  SuiteDetail,
  SuiteSummary,
} from "./types";

const API_BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

export const api = {
  listBenchmarks(): Promise<SuiteSummary[]> {
    return request("/benchmarks");
  },

  getBenchmark(id: string): Promise<SuiteDetail> {
    return request(`/benchmarks/${encodeURIComponent(id)}`);
  },

  listRuns(): Promise<RunSummary[]> {
    return request("/runs");
  },

  getRun(runId: string): Promise<RunDetail> {
    return request(`/runs/${encodeURIComponent(runId)}`);
  },

  deleteRun(runId: string): Promise<void> {
    return request(`/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  },

  async getRunJob(runId: string): Promise<RunJob | null> {
    const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/job`);
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) {
          detail = body.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new Error(detail);
    }
    return (await response.json()) as RunJob;
  },

  getTaskOutput(runId: string, taskId: string): Promise<string> {
    return request(
      `/runs/${encodeURIComponent(runId)}/results/${encodeURIComponent(taskId)}/output`,
    );
  },

  listProviders(): Promise<Provider[]> {
    return request("/providers");
  },

  listProviderModels(name: string): Promise<ModelsResponse> {
    return request(`/providers/${encodeURIComponent(name)}/models`);
  },

  async createRun(body: CreateRunRequest): Promise<CreateRunResponse> {
    const response = await request<CreateRunResponse>("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.run_id) {
      return response;
    }
    const runId = await api.waitForRunId(response.job_id);
    return { ...response, run_id: runId };
  },

  async waitForRunId(jobId: string, timeoutMs = 30_000): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const job = await api.getJob(jobId);
      if (job.run_id) {
        return job.run_id;
      }
      if (job.status === "error") {
        throw new Error(job.error ?? "Run failed");
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    throw new Error("Timed out waiting for run ID");
  },

  prompt(body: PromptRequest): Promise<PromptResponse> {
    return request("/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  getJob(jobId: string): Promise<JobStatus> {
    return request(`/jobs/${encodeURIComponent(jobId)}`);
  },

  createCompare(body: CreateCompareRequest): Promise<CreateCompareResponse> {
    return request("/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  listComparisons(): Promise<ComparisonSummary[]> {
    return request("/comparisons");
  },

  getComparison(id: string): Promise<ComparisonDetail> {
    return request(`/comparisons/${encodeURIComponent(id)}`);
  },

  async buildReport(body: ReportRequest): Promise<LeaderboardReport | string> {
    const response = await fetch(`${API_BASE}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) {
          detail = payload.detail;
        }
      } catch {
        // ignore
      }
      throw new Error(detail);
    }
    if (body.format === "json") {
      return (await response.json()) as LeaderboardReport;
    }
    return response.text();
  },
};

export const queryKeys = {
  benchmarks: ["benchmarks"] as const,
  benchmark: (id: string) => ["benchmarks", id] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  runJob: (id: string) => ["runs", id, "job"] as const,
  taskOutput: (runId: string, taskId: string) =>
    ["runs", runId, "output", taskId] as const,
  providers: ["providers"] as const,
  providerModels: (name: string) => ["providers", name, "models"] as const,
  job: (id: string) => ["jobs", id] as const,
  comparisons: ["comparisons"] as const,
  comparison: (id: string) => ["comparisons", id] as const,
  leaderboard: (runIds: string[]) => ["leaderboard", ...runIds] as const,
};
