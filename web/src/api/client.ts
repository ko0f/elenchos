import type {
  CreateRunRequest,
  CreateRunResponse,
  JobStatus,
  ModelsResponse,
  PromptRequest,
  PromptResponse,
  Provider,
  RunDetail,
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

  createRun(body: CreateRunRequest): Promise<CreateRunResponse> {
    return request("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
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
};

export const queryKeys = {
  benchmarks: ["benchmarks"] as const,
  benchmark: (id: string) => ["benchmarks", id] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  taskOutput: (runId: string, taskId: string) =>
    ["runs", runId, "output", taskId] as const,
  providers: ["providers"] as const,
  providerModels: (name: string) => ["providers", name, "models"] as const,
  job: (id: string) => ["jobs", id] as const,
};
