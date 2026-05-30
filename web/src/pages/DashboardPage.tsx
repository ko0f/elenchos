import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { ScoreBadge } from "../components/ScoreBadge";
import { formatDate, meanScore } from "../lib/format";
import "../components/RunLauncher.css";
import "../components/RunPicker.css";

export function DashboardPage() {
  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });
  const { data: comparisons = [], isLoading: comparisonsLoading } = useQuery({
    queryKey: queryKeys.comparisons,
    queryFn: api.listComparisons,
  });

  const recentRuns = runs.slice(0, 5);
  const recentComparisons = comparisons.slice(0, 5);

  return (
    <>
      <header className="page-header">
        <h1>Dashboard</h1>
        <p className="page-header__subtitle">Recent activity and quick links.</p>
      </header>

      <div className="dashboard-links page-header__actions">
        <Link to="/benchmarks" className="btn">
          Benchmarks
        </Link>
        <Link to="/runs" className="btn">
          Runs
        </Link>
        <Link to="/leaderboard" className="btn">
          Leaderboard
        </Link>
        <Link to="/prompt" className="btn">
          Quick prompt
        </Link>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-panel">
          <h2>Recent runs</h2>
          {runsLoading ? (
            <p className="page-header__subtitle">Loading…</p>
          ) : recentRuns.length === 0 ? (
            <p className="page-header__subtitle">No runs yet.</p>
          ) : (
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Benchmark</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <Link to={`/runs/${run.run_id}`}>{run.run_id}</Link>
                    </td>
                    <td>{run.benchmark?.id ?? "—"}</td>
                    <td>
                      <ScoreBadge score={meanScore(run.summary)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="dashboard-panel">
          <h2>Recent comparisons</h2>
          {comparisonsLoading ? (
            <p className="page-header__subtitle">Loading…</p>
          ) : recentComparisons.length === 0 ? (
            <p className="page-header__subtitle">No comparisons yet.</p>
          ) : (
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Benchmark</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {recentComparisons.map((item) => (
                  <tr key={item.comparison_id}>
                    <td>
                      <Link to={`/comparisons/${item.comparison_id}`}>
                        {item.comparison_id}
                      </Link>
                    </td>
                    <td>{item.benchmark_id}</td>
                    <td>{formatDate(item.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}
