import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { LeaderboardReport } from "../api/types";
import { RunPicker } from "../components/RunPicker";
import { ScoreBadge } from "../components/ScoreBadge";
import { canBuildLeaderboard } from "../lib/runs";
import "../components/RunLauncher.css";
import "../components/RunPicker.css";

function downloadExport(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function LeaderboardPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const [report, setReport] = useState<LeaderboardReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { data: runs = [], isLoading } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });

  const canGenerate = canBuildLeaderboard(selected, runs);

  async function generateReport() {
    if (!canGenerate) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await api.buildReport({ run_ids: selected, format: "json" });
      if (typeof payload === "string") {
        throw new Error("Unexpected text response");
      }
      setReport(payload);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Report failed");
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  async function exportFormat(format: "md" | "csv" | "json") {
    if (!canGenerate) {
      return;
    }
    const payload = await api.buildReport({ run_ids: selected, format });
    if (typeof payload === "string") {
      const mime =
        format === "md" ? "text/markdown" : format === "csv" ? "text/csv" : "application/json";
      downloadExport(`leaderboard.${format}`, payload, mime);
      return;
    }
    downloadExport("leaderboard.json", JSON.stringify(payload, null, 2), "application/json");
  }

  if (isLoading) {
    return <div className="page-state">Loading runs…</div>;
  }

  return (
    <>
      <header className="page-header">
        <h1>Leaderboard</h1>
        <p className="page-header__subtitle">
          Select runs from the same benchmark to aggregate scores.
        </p>
      </header>

      <RunPicker runs={runs} selected={selected} onChange={setSelected} />

      <div className="selection-actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={!canGenerate || loading}
          onClick={() => void generateReport()}
        >
          {loading ? "Generating…" : "Generate leaderboard"}
        </button>
        {!canGenerate && selected.length > 0 && (
          <span className="selection-actions__hint">Runs must share the same benchmark.</span>
        )}
      </div>

      {error && <div className="run-launcher__error">{error}</div>}

      {report && (
        <>
          <table className="leaderboard-table" aria-label="Leaderboard results">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>Run ID</th>
                <th>Mean score</th>
                <th>Pass rate</th>
                <th>P95 latency</th>
                {report.runs.some((row) => row.win_rate != null) && <th>Win rate</th>}
              </tr>
            </thead>
            <tbody>
              {report.runs.map((row) => (
                <tr key={row.run_id}>
                  <td>{row.rank ?? "—"}</td>
                  <td>{row.model}</td>
                  <td className="mono">{row.run_id}</td>
                  <td>
                    <ScoreBadge score={row.mean_score} />
                  </td>
                  <td>
                    {row.pass_rate != null ? `${Math.round(row.pass_rate * 100)}%` : "—"}
                  </td>
                  <td>
                    {row.p95_latency_ms != null ? `${Math.round(row.p95_latency_ms)} ms` : "—"}
                  </td>
                  {report.runs.some((item) => item.win_rate != null) && (
                    <td>{row.win_rate != null ? `${Math.round(row.win_rate * 100)}%` : "—"}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          <div className="export-actions">
            <button type="button" className="btn" onClick={() => void exportFormat("md")}>
              Export MD
            </button>
            <button type="button" className="btn" onClick={() => void exportFormat("csv")}>
              Export CSV
            </button>
            <button type="button" className="btn" onClick={() => void exportFormat("json")}>
              Export JSON
            </button>
          </div>
        </>
      )}
    </>
  );
}
