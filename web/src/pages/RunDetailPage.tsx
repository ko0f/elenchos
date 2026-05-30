import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { TaskDoneData } from "../api/types";
import { formatDate, formatScore, meanScore } from "../lib/format";
import { jobStatusLabel } from "../lib/jobStatusLabel";
import { aggregateResultsSummary } from "../lib/runSummary";
import { useJobStream } from "../hooks/useJobStream";
import { ResultsTable } from "../components/ResultsTable";
import { ScoreBadge } from "../components/ScoreBadge";
import "../components/RunProgress.css";

const LIVE_POLL_MS = 2000;

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
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => api.getRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data?.run.finished_at ? false : LIVE_POLL_MS,
  });

  const isLive = Boolean(data && !data.run.finished_at);

  const { data: runJob } = useQuery({
    queryKey: queryKeys.runJob(runId),
    queryFn: () => api.getRunJob(runId),
    enabled: isLive,
    retry: false,
    refetchInterval: isLive ? LIVE_POLL_MS : false,
  });

  const { events, status: streamStatus } = useJobStream(runJob?.job_id ?? null);

  const benchmarkId = data?.run.benchmark?.id;
  const { data: benchmark } = useQuery({
    queryKey: queryKeys.benchmark(benchmarkId ?? ""),
    queryFn: () => api.getBenchmark(benchmarkId!),
    enabled: isLive && Boolean(benchmarkId),
  });

  useEffect(() => {
    if (data?.run.finished_at) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runJob(runId) });
    }
  }, [data?.run.finished_at, queryClient, runId]);

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
  const taskEvents = events.filter((item) => item.event === "task_done");
  const lastTaskEvent = taskEvents[taskEvents.length - 1]?.data as unknown as
    | TaskDoneData
    | undefined;
  const totalTasks = lastTaskEvent?.total ?? benchmark?.tasks.length;
  const completedTasks = results.length;
  const progressPct =
    totalTasks != null && totalTasks > 0
      ? Math.round((completedTasks / totalTasks) * 100)
      : 0;

  const summary =
    run.summary ??
    (results.length > 0 ? aggregateResultsSummary(results) : null);
  const statusLabel = jobStatusLabel(
    runJob ? streamStatus : null,
    isLive && !runJob,
  );

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / {run.run_id}
        </p>
        <div className="page-header__title-row">
          <h1>{run.run_id}</h1>
          {isLive && statusLabel && (
            <span className="run-progress__status page-header__live">{statusLabel}</span>
          )}
        </div>
        <p className="page-header__subtitle">
          {run.model}
          {run.benchmark ? ` · ${run.benchmark.id}` : ""} · {formatDate(run.started_at)}
        </p>
      </header>

      {isLive && totalTasks != null && (
        <div className="run-live-progress">
          <div className="run-progress__bar-wrap">
            <div className="run-progress__bar" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="run-progress__count">
            {completedTasks} / {totalTasks} tasks
          </p>
        </div>
      )}

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
          <div className="metric-card__value">
            {totalTasks != null ? `${completedTasks} / ${totalTasks}` : results.length}
          </div>
        </div>
      </div>

      <ResultsTable runId={run.run_id} results={results} />
    </>
  );
}
