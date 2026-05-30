import { Fragment, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { FaIcon } from "../components/FaIcon";
import { formatDate } from "../lib/format";
import "../components/RunPicker.css";
import "./RunDetailPage.css";

function formatPct(value: unknown): string {
  if (typeof value !== "number") {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

export function ComparisonDetailPage() {
  const { comparisonId = "" } = useParams();
  const queryClient = useQueryClient();
  const [pinError, setPinError] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.comparison(comparisonId),
    queryFn: () => api.getComparison(comparisonId),
    enabled: Boolean(comparisonId),
  });

  const pinMutation = useMutation({
    mutationFn: api.pinComparisonBaselineSource,
    onSuccess: (updated) => {
      setPinError(null);
      queryClient.setQueryData(queryKeys.comparison(comparisonId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
    onError: (err) => {
      setPinError(
        err instanceof Error ? err.message : "Failed to pin comparison",
      );
    },
  });

  const unpinMutation = useMutation({
    mutationFn: api.unpinComparisonBaselineSource,
    onSuccess: (updated) => {
      setPinError(null);
      queryClient.setQueryData(queryKeys.comparison(comparisonId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
    onError: (err) => {
      setPinError(
        err instanceof Error ? err.message : "Failed to unpin comparison",
      );
    },
  });

  if (isLoading) {
    return <div className="page-state">Loading comparison…</div>;
  }

  if (isError) {
    return (
      <div className="page-state page-state--error">
        {error instanceof Error ? error.message : "Failed to load comparison"}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const summary = data.summary ?? {};
  const wins = summary.wins as Record<string, number> | undefined;
  const winRate = summary.win_rate as Record<string, number> | undefined;
  const meanScore = summary.mean_score as Record<string, number> | undefined;
  const runLabel = Object.fromEntries(data.runs.map((run) => [run.run_id, run.model]));
  const canPin = data.mode === "rubric";
  const isPinned = Boolean(data.is_baseline_source);
  const pinBusy = pinMutation.isPending || unpinMutation.isPending;
  const hasBaseline = Boolean(data.baseline_run_id);

  function toggleBaselineSource() {
    if (pinBusy || !canPin) {
      return;
    }
    if (isPinned) {
      unpinMutation.mutate(comparisonId);
    } else {
      pinMutation.mutate(comparisonId);
    }
  }

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / {data.comparison_id}
        </p>
        <div className="page-header__title-row">
          <h1>{data.comparison_id}</h1>
          {canPin && (
            <button
              type="button"
              className={`baseline-star${isPinned ? " baseline-star--active" : ""}`}
              aria-label={
                isPinned
                  ? `Stop using ${data.comparison_id} for vs-baseline scores`
                  : `Use ${data.comparison_id} for vs-baseline scores`
              }
              disabled={pinBusy || (!isPinned && !hasBaseline)}
              title={
                !hasBaseline && !isPinned
                  ? "Set a baseline run on Runs first"
                  : undefined
              }
              onClick={toggleBaselineSource}
            >
              <FaIcon icon="star" variant={isPinned ? "solid" : "regular"} />
            </button>
          )}
        </div>
        <p className="page-header__subtitle">
          {data.benchmark_id} · {data.mode} · judge {data.judge_model} ·{" "}
          {formatDate(data.started_at)}
          {isPinned ? " · vs-baseline source" : ""}
        </p>
        {pinError && (
          <p className="page-header__subtitle page-header__subtitle--error">
            {pinError}
          </p>
        )}
        {canPin && !hasBaseline && !isPinned && (
          <p className="page-header__subtitle">
            Star a baseline run on <Link to="/runs">Runs</Link> before pinning this
            comparison.
          </p>
        )}
      </header>

      <div className="compare-summary">
        {data.runs.map((run) => (
          <div key={run.run_id} className="metric-card">
            <div className="metric-card__label">{run.model}</div>
            <div className="metric-card__value">
              {wins ? `${wins[run.run_id] ?? 0} wins` : null}
              {winRate ? formatPct(winRate[run.run_id]) : null}
              {meanScore ? meanScore[run.run_id]?.toFixed(2) : null}
            </div>
            <div className="metric-card__label mono">{run.run_id}</div>
          </div>
        ))}
      </div>

      <table className="leaderboard-table compare-task-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Winner</th>
            {data.mode === "rubric" && data.runs.map((run) => <th key={run.run_id}>{run.model}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.tasks.map((task) => {
            const colSpan = 2 + (data.mode === "rubric" ? data.runs.length : 0);
            return (
              <Fragment key={task.task_id}>
                <tr className="compare-task-table__main">
                  <td>{task.task_id}</td>
                  <td className="mono">
                    {runLabel[task.winner_run_id ?? ""] ?? task.winner_run_id ?? "tie"}
                  </td>
                  {data.mode === "rubric" &&
                    data.runs.map((run) => (
                      <td key={run.run_id}>{task.scores?.[run.run_id]?.toFixed(2) ?? "—"}</td>
                    ))}
                </tr>
                <tr className="compare-task-table__rationale">
                  <td colSpan={colSpan}>{task.rationale ?? "—"}</td>
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
