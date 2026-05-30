import type { TaskResult } from "../api/types";

function mean(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentile(values: number[], pct: number): number | null {
  if (values.length === 0) {
    return null;
  }
  const ordered = [...values].sort((a, b) => a - b);
  const index = Math.round((ordered.length - 1) * pct);
  return ordered[index] ?? null;
}

/** Interim run summary from partial task results (matches server aggregate_run_summary). */
export function aggregateResultsSummary(results: TaskResult[]): Record<string, number> {
  const total = results.length;
  const successful = results.filter((result) => result.error == null);
  const errors = total - successful.length;
  const scored = successful.filter((result) => result.score != null);
  const latencies = successful.map((result) => result.latency_ms);
  const passCount = scored.filter((result) => (result.score ?? 0) >= 1.0).length;

  const summary: Record<string, number> = {
    task_count: total,
    errors,
  };

  const meanScore = mean(scored.map((result) => result.score as number));
  if (meanScore != null) {
    summary.mean_score = meanScore;
  }
  if (total > 0) {
    summary.pass_rate = passCount / total;
  }
  const p95 = percentile(latencies, 0.95);
  if (p95 != null) {
    summary.p95_latency_ms = p95;
  }

  return summary;
}
