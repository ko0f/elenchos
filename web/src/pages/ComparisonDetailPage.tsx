import { Fragment } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { formatDate } from "../lib/format";
import "../components/RunPicker.css";

function formatPct(value: unknown): string {
  if (typeof value !== "number") {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

export function ComparisonDetailPage() {
  const { comparisonId = "" } = useParams();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.comparison(comparisonId),
    queryFn: () => api.getComparison(comparisonId),
    enabled: Boolean(comparisonId),
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

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / {data.comparison_id}
        </p>
        <h1>{data.comparison_id}</h1>
        <p className="page-header__subtitle">
          {data.benchmark_id} · {data.mode} · judge {data.judge_model} ·{" "}
          {formatDate(data.started_at)}
        </p>
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
