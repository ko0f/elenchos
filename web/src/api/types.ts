export interface BenchmarkRef {
  id: string;
  version: number;
}

export interface SuiteSummary {
  id: string;
  version: number;
  type: string;
  description: string;
  task_count: number;
  source: string;
}

export interface GenerationParams {
  temperature?: number;
  max_tokens?: number | null;
  top_p?: number | null;
  seed?: number | null;
  stop?: string[] | null;
}

export interface SuiteDefaults {
  params?: GenerationParams | null;
}

export interface Task {
  id: string;
  type: string;
  prompt: string;
  scorers: string[];
}

export interface SuiteDetail {
  id: string;
  version: number;
  type: string;
  description: string;
  defaults?: SuiteDefaults | null;
  tasks: Task[];
  requires_code_exec: boolean;
  requires_judge: boolean;
}

export interface RunSummary {
  run_id: string;
  started_at: string;
  model: string;
  benchmark?: BenchmarkRef | null;
  finished_at?: string | null;
  summary?: Record<string, unknown> | null;
}

export interface RunMetadata {
  run_id: string;
  started_at: string;
  finished_at?: string | null;
  model: string;
  params: Record<string, unknown>;
  tool_version: string;
  benchmark?: BenchmarkRef | null;
  summary?: Record<string, unknown> | null;
}

export interface TaskResult {
  task_id: string;
  latency_ms: number;
  prompt?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  output?: string | null;
  score?: number | null;
  scorer?: string | null;
  passed?: number | null;
  total?: number | null;
  finish_reason?: string | null;
  error?: string | null;
}

export interface RunDetail {
  run: RunMetadata;
  results: TaskResult[];
}

export interface Provider {
  name: string;
  base_url: string;
  healthy: boolean;
}

export interface ApiError {
  detail: string;
}

export interface ModelsResponse {
  models: string[];
}

export interface CreateRunRequest {
  benchmark: string;
  model: string;
  temperature?: number;
  max_tokens?: number;
  concurrency?: number;
  allow_code_exec?: boolean;
  judge?: string;
}

export interface CreateRunResponse {
  job_id: string;
  run_id?: string | null;
}

export interface PromptRequest {
  model: string;
  text: string;
}

export interface PromptResponse {
  run_id: string;
  output?: string | null;
  latency_ms: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  finish_reason?: string | null;
  error?: string | null;
}

export interface ProgressEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface JobStatus {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  run_id?: string | null;
  progress: ProgressEvent[];
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface TaskDoneData {
  task_id: string;
  index: number;
  total: number;
  score?: number | null;
  error?: string | null;
}
