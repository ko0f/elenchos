import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { TaskDoneData } from "../api/types";
import { formatDate, formatDuration, formatScore, meanScore } from "../lib/format";
import { jobStatusLabel } from "../lib/jobStatusLabel";
import { aggregateResultsSummary, totalLatencyMs } from "../lib/runSummary";
import { useJobStream } from "../hooks/useJobStream";
import { BaselineComparison } from "../components/BaselineComparison";
import { BaselineScoreBadge } from "../components/BaselineScoreBadge";
import { FaIcon } from "../components/FaIcon";
import { ResultsTable } from "../components/ResultsTable";
import { ScoreBadge } from "../components/ScoreBadge";
import "../components/RunProgress.css";
import "./RunDetailPage.css";

const LIVE_POLL_MS = 2000;
const MAX_JOB_LOOKUP_POLLS = 3;

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
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const [jobLookupCount, setJobLookupCount] = useState(0);
  const shouldPollLiveRef = useRef(true);

  useEffect(() => {
    setJobLookupCount(0);
    shouldPollLiveRef.current = true;
  }, [runId]);

  const setBaselineMutation = useMutation({
    mutationFn: api.setBaseline,
    onSuccess: () => {
      setBaselineError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
    onError: (err) => {
      setBaselineError(
        err instanceof Error ? err.message : "Failed to set baseline",
      );
    },
  });

  const clearBaselineMutation = useMutation({
    mutationFn: api.clearBaseline,
    onSuccess: () => {
      setBaselineError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
    onError: (err) => {
      setBaselineError(
        err instanceof Error ? err.message : "Failed to clear baseline",
      );
    },
  });

  const baselineBusy =
    setBaselineMutation.isPending || clearBaselineMutation.isPending;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.run(runId),
    queryFn: () => api.getRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      if (query.state.data?.run.finished_at || !shouldPollLiveRef.current) {
        return false;
      }
      return LIVE_POLL_MS;
    },
  });

  const isLive = Boolean(data && !data.run.finished_at);

  const { data: runJob } = useQuery({
    queryKey: queryKeys.runJob(runId),
    queryFn: async () => {
      const job = await api.getRunJob(runId);
      if (job == null) {
        setJobLookupCount((count) => count + 1);
      }
      return job;
    },
    enabled: isLive && jobLookupCount < MAX_JOB_LOOKUP_POLLS,
    retry: false,
    refetchInterval: (query) => {
      if (!isLive || query.state.data?.job_id) {
        return false;
      }
      return jobLookupCount < MAX_JOB_LOOKUP_POLLS ? LIVE_POLL_MS : false;
    },
  });

  const jobLookupExhausted =
    isLive && runJob == null && jobLookupCount >= MAX_JOB_LOOKUP_POLLS;
  const shouldPollLive = isLive && (Boolean(runJob?.job_id) || !jobLookupExhausted);
  const shouldPollJob = shouldPollLive && !runJob?.job_id;
  const isOrphaned = jobLookupExhausted;

  shouldPollLiveRef.current = shouldPollLive;

  const { events, status: streamStatus } = useJobStream(runJob?.job_id ?? null);

  const benchmarkId = data?.run.benchmark?.id;
  const { data: benchmark } = useQuery({
    queryKey: queryKeys.benchmark(benchmarkId ?? ""),
    queryFn: () => api.getBenchmark(benchmarkId!),
    enabled: shouldPollLive && Boolean(benchmarkId),
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
  const statusLabel = isOrphaned
    ? "Interrupted"
    : jobStatusLabel(runJob ? streamStatus : null, shouldPollJob);
  const isBaseline = Boolean(data.baseline_comparison?.is_baseline);

  function toggleBaseline() {
    if (baselineBusy) {
      return;
    }
    if (isBaseline) {
      clearBaselineMutation.mutate(run.run_id);
    } else {
      setBaselineMutation.mutate(run.run_id);
    }
  }

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / {run.run_id}
        </p>
        <div className="page-header__title-row">
          <h1>{run.run_id}</h1>
          <button
            type="button"
            className={`baseline-star${isBaseline ? " baseline-star--active" : ""}`}
            aria-label={
              isBaseline
                ? `Clear baseline for ${run.run_id}`
                : `Set ${run.run_id} as baseline`
            }
            disabled={baselineBusy}
            onClick={toggleBaseline}
          >
            <FaIcon icon="star" variant={isBaseline ? "solid" : "regular"} />
          </button>
          {statusLabel && (
            <span
              className={
                isOrphaned
                  ? "run-progress__status page-header__live page-header__live--orphaned"
                  : "run-progress__status page-header__live"
              }
            >
              {statusLabel}
            </span>
          )}
        </div>
        <p className="page-header__subtitle">
          {run.model}
          {run.benchmark ? ` · ${run.benchmark.id}` : ""} · {formatDate(run.started_at)}
        </p>
        {baselineError && (
          <p className="page-header__subtitle page-header__subtitle--error">
            {baselineError}
          </p>
        )}
      </header>

      {shouldPollLive && totalTasks != null && (
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
        {data.baseline_comparison && (
          <div className="metric-card">
            <div className="metric-card__label">vs Baseline</div>
            <div className="metric-card__value">
              <BaselineScoreBadge
                score={data.baseline_comparison.relative_score}
                isBaseline={data.baseline_comparison.is_baseline}
              />
            </div>
          </div>
        )}
        <div className="metric-card">
          <div className="metric-card__label">Pass rate</div>
          <div className="metric-card__value">
            {metricValue(summary, "pass_rate")}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-card__label">Total time</div>
          <div className="metric-card__value">
            {formatDuration(totalLatencyMs(results))}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-card__label">Tasks</div>
          <div className="metric-card__value">
            {totalTasks != null ? `${completedTasks} / ${totalTasks}` : results.length}
          </div>
        </div>
      </div>

      <ResultsTable runId={run.run_id} results={results} runParams={run.params} />

      {data.baseline_comparison && (
        <BaselineComparison comparison={data.baseline_comparison} />
      )}
    </>
  );
}
