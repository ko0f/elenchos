import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { BaselineScoreBadge } from "../components/BaselineScoreBadge";
import { FaIcon } from "../components/FaIcon";
import { ScoreBadge } from "../components/ScoreBadge";
import { formatDate, meanScore } from "../lib/format";
import { canCompareRuns } from "../lib/runs";
import "../components/RunLauncher.css";
import "../components/RunPicker.css";
import "./RunsPage.css";

export function RunsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteRun,
    onSuccess: (_data, runId) => {
      setDeleteError(null);
      setSelected((ids) => ids.filter((id) => id !== runId));
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
    onError: (err) => {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete run");
    },
  });

  const setBaselineMutation = useMutation({
    mutationFn: api.setBaseline,
    onSuccess: () => {
      setBaselineError(null);
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

  const compareEnabled = useMemo(
    () => (data ? canCompareRuns(selected, data) : false),
    [selected, data],
  );

  function goCompare() {
    void navigate(`/compare?runs=${selected.map(encodeURIComponent).join(",")}`);
  }

  function confirmDelete(runId: string) {
    if (!window.confirm(`Delete run ${runId}? This cannot be undone.`)) {
      return;
    }
    deleteMutation.mutate(runId);
  }

  function toggleBaseline(runId: string, isBaseline: boolean) {
    if (baselineBusy) {
      return;
    }
    if (isBaseline) {
      clearBaselineMutation.mutate(runId);
    } else {
      setBaselineMutation.mutate(runId);
    }
  }

  if (isLoading) {
    return <div className="page-state">Loading runs…</div>;
  }

  if (isError) {
    return (
      <div className="page-state page-state--error">
        {error instanceof Error ? error.message : "Failed to load runs"}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <>
        <header className="page-header">
          <h1>Runs</h1>
          <p className="page-header__subtitle">Past benchmark run results.</p>
        </header>
        <div className="page-state">No runs yet.</div>
      </>
    );
  }

  return (
    <>
      <header className="page-header">
        <h1>Runs</h1>
        <p className="page-header__subtitle">
          Star a run as the benchmark baseline; other runs show relative score.
        </p>
      </header>

      <div className="selection-actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={!compareEnabled}
          onClick={goCompare}
        >
          Compare selected
        </button>
        <Link to="/leaderboard" className="btn">
          Leaderboard
        </Link>
        {selected.length > 0 && !compareEnabled && (
          <span className="selection-actions__hint">
            Compare needs 2+ runs from the same benchmark.
          </span>
        )}
        {deleteError && (
          <span className="selection-actions__hint selection-actions__hint--error">
            {deleteError}
          </span>
        )}
        {baselineError && (
          <span className="selection-actions__hint selection-actions__hint--error">
            {baselineError}
          </span>
        )}
      </div>

      <table className="runs-table">
        <thead>
          <tr>
            <th aria-label="Select" />
            <th aria-label="Baseline" className="runs-table__baseline-col">
              Baseline
            </th>
            <th>Run ID</th>
            <th>Started</th>
            <th>Benchmark</th>
            <th>Model</th>
            <th>Mean score</th>
            <th>vs Baseline</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {data.map((run) => (
            <tr key={run.run_id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Select ${run.run_id}`}
                  checked={selected.includes(run.run_id)}
                  onChange={() => {
                    if (selected.includes(run.run_id)) {
                      setSelected(selected.filter((id) => id !== run.run_id));
                    } else {
                      setSelected([...selected, run.run_id]);
                    }
                  }}
                />
              </td>
              <td className="runs-table__baseline-col">
                <button
                  type="button"
                  className={`baseline-star${run.is_baseline ? " baseline-star--active" : ""}`}
                  aria-label={
                    run.is_baseline
                      ? `Clear baseline for ${run.run_id}`
                      : `Set ${run.run_id} as baseline`
                  }
                  disabled={baselineBusy}
                  onClick={() => toggleBaseline(run.run_id, Boolean(run.is_baseline))}
                >
                  <FaIcon
                    icon="star"
                    variant={run.is_baseline ? "solid" : "regular"}
                  />
                </button>
              </td>
              <td>
                <Link to={`/runs/${run.run_id}`}>{run.run_id}</Link>
              </td>
              <td>{formatDate(run.started_at)}</td>
              <td>{run.benchmark?.id ?? "—"}</td>
              <td>{run.model}</td>
              <td>
                <ScoreBadge score={meanScore(run.summary)} />
              </td>
              <td>
                <BaselineScoreBadge
                  score={run.baseline_score}
                  isBaseline={run.is_baseline}
                />
              </td>
              <td>
                <button
                  type="button"
                  className="btn btn--danger btn--sm btn--icon"
                  aria-label={`Delete ${run.run_id}`}
                  disabled={deleteMutation.isPending}
                  onClick={() => confirmDelete(run.run_id)}
                >
                  <FaIcon icon="trash-can" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
