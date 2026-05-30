import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { formatDate, meanScore } from "../lib/format";
import { ScoreBadge } from "../components/ScoreBadge";

export function RunsPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });

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
        <p className="page-header__subtitle">Past benchmark run results.</p>
      </header>

      <table className="runs-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Started</th>
            <th>Benchmark</th>
            <th>Model</th>
            <th>Mean score</th>
          </tr>
        </thead>
        <tbody>
          {data.map((run) => (
            <tr key={run.run_id}>
              <td>
                <Link to={`/runs/${run.run_id}`}>{run.run_id}</Link>
              </td>
              <td>{formatDate(run.started_at)}</td>
              <td>{run.benchmark?.id ?? "—"}</td>
              <td>{run.model}</td>
              <td>
                <ScoreBadge score={meanScore(run.summary)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
