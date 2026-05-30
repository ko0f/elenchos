import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { formatDate, formatScore, meanScore } from "../lib/format";
import { ResultsTable } from "../components/ResultsTable";
import { ScoreBadge } from "../components/ScoreBadge";

function metricValue(summary: Record<string, unknown> | null | undefined, key: string): string {
  const value = summary?.[key];
  if (typeof value === "number") {
    if (key.includes("rate")) {
      return `${(value * 100).toFixed(0)}%`;
    }
    if (key.includes("latency")) {
      return `${Math.round(value)} ms`;
    }
    return formatScore(value);
  }
  return "—";
}

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => api.getRun(runId),
    enabled: Boolean(runId),
  });

  if (isLoading) {
    return <div className="page-state">Loading run…</div>;
  }

  if (isError) {
    return (
      <div className="page-state page-state--error">
        {error instanceof Error ? error.message : "Failed to load run"}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { run, results } = data;
  const summary = run.summary;

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / {run.run_id}
        </p>
        <h1>{run.run_id}</h1>
        <p className="page-header__subtitle">
          {run.model}
          {run.benchmark ? ` · ${run.benchmark.id}` : ""} · {formatDate(run.started_at)}
        </p>
      </header>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-card__label">Mean score</div>
          <div className="metric-card__value">
            <ScoreBadge score={meanScore(summary)} />
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-card__label">Pass rate</div>
          <div className="metric-card__value">
            {metricValue(summary, "pass_rate")}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-card__label">P95 latency</div>
          <div className="metric-card__value">
            {metricValue(summary, "p95_latency_ms")}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-card__label">Tasks</div>
          <div className="metric-card__value">{results.length}</div>
        </div>
      </div>

      <ResultsTable runId={run.run_id} results={results} />
    </>
  );
}
