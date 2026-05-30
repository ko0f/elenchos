import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { ComparisonSummary } from "../api/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { FaIcon } from "../components/FaIcon";
import { RunDurationCell } from "../components/RunDurationCell";
import { RunTableProgressCell } from "../components/RunTableProgressCell";
import { formatDate } from "../lib/format";
import { canCompareRuns } from "../lib/runs";
import "../components/RunLauncher.css";
import "../components/RunPicker.css";

export function RunsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((run) => !run.finished_at) ? 2000 : false;
    },
  });
  const {
    data: comparisons = [],
    isLoading: comparisonsLoading,
    isError: comparisonsError,
    error: comparisonsFetchError,
  } = useQuery({
    queryKey: queryKeys.comparisons,
    queryFn: api.listComparisons,
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

  const runs = data ?? [];

  return (
    <>
      <header className="page-header">
        <h1>Runs</h1>
        <p className="page-header__subtitle">Past benchmark run results.</p>
      </header>

      {runs.length > 0 && (
        <>
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
          </div>

          <table className="runs-table">
            <thead>
              <tr>
                <th aria-label="Select" />
                <th>Started</th>
                <th>Benchmark</th>
                <th>Model</th>
                <th>Duration</th>
                <th>vs Baseline</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.run_id}
                  className="runs-table__row"
                  tabIndex={0}
                  aria-label={`View run: ${run.model}, ${run.benchmark?.id ?? "unknown benchmark"}`}
                  onClick={() => navigate(`/runs/${run.run_id}`)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      navigate(`/runs/${run.run_id}`);
                    }
                  }}
                >
                  <td onClick={(event) => event.stopPropagation()}>
                    {!run.is_baseline && (
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
                    )}
                  </td>
                  <td>{formatDate(run.started_at)}</td>
                  <td>{run.benchmark?.id ?? "—"}</td>
                  <td>{run.model}</td>
                  <td>
                    <RunDurationCell
                      startedAt={run.started_at}
                      finishedAt={run.finished_at}
                    />
                  </td>
                  <td>
                    <RunTableProgressCell
                      runId={run.run_id}
                      finishedAt={run.finished_at}
                      benchmarkId={run.benchmark?.id}
                      baselineScore={run.baseline_score}
                      isBaseline={run.is_baseline}
                    />
                  </td>
                  <td onClick={(event) => event.stopPropagation()}>
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
      )}

      {runs.length === 0 && <div className="page-state">No runs yet.</div>}

      <ComparisonsSection
        comparisons={comparisons}
        isLoading={comparisonsLoading}
        isError={comparisonsError}
        error={comparisonsFetchError}
        onSelect={(comparisonId) => navigate(`/comparisons/${comparisonId}`)}
      />
    </>
  );
}

interface ComparisonsSectionProps {
  comparisons: ComparisonSummary[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  onSelect: (comparisonId: string) => void;
}

function ComparisonsSection({
  comparisons,
  isLoading,
  isError,
  error,
  onSelect,
}: ComparisonsSectionProps) {
  return (
    <section className="runs-page-section">
      <h2 className="runs-page-section__title">Comparisons</h2>
      {isLoading ? (
        <div className="page-state">Loading comparisons…</div>
      ) : isError ? (
        <div className="page-state page-state--error">
          {error instanceof Error ? error.message : "Failed to load comparisons"}
        </div>
      ) : comparisons.length === 0 ? (
        <div className="page-state">No comparisons yet.</div>
      ) : (
        <table className="runs-table" aria-label="Comparisons">
          <thead>
            <tr>
              <th>Started</th>
              <th>Benchmark</th>
              <th>Mode</th>
              <th>Judge</th>
              <th>Runs</th>
              <th>Comparison</th>
            </tr>
          </thead>
          <tbody>
            {comparisons.map((item) => (
              <tr
                key={item.comparison_id}
                className="runs-table__row"
                tabIndex={0}
                aria-label={`View comparison: ${item.comparison_id}`}
                onClick={() => onSelect(item.comparison_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(item.comparison_id);
                  }
                }}
              >
                <td>{formatDate(item.started_at)}</td>
                <td>{item.benchmark_id}</td>
                <td>{item.mode}</td>
                <td>{item.judge_model}</td>
                <td>{item.run_ids.length}</td>
                <td>
                  <Link
                    to={`/comparisons/${item.comparison_id}`}
                    className="mono"
                    onClick={(event) => event.stopPropagation()}
                  >
                    {item.comparison_id}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
