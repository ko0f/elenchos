import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { CompareProgress } from "../components/CompareProgress";
import "../components/RunLauncher.css";
import "./ComparePage.css";

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialRuns = useMemo(
    () => searchParams.get("runs")?.split(",").filter(Boolean) ?? [],
    [searchParams],
  );
  const [mode, setMode] = useState(initialRuns.length === 2 ? "pairwise" : "rubric");
  const [judge, setJudge] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: runs = [] } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });

  const selectedRuns = runs.filter((run) => initialRuns.includes(run.run_id));
  const canSubmit =
    initialRuns.length >= 2 &&
    judge.trim().length > 0 &&
    (mode !== "pairwise" || initialRuns.length === 2) &&
    !submitting &&
    !jobId;

  const handleFinished = useCallback(
    (comparisonId: string) => {
      void navigate(`/comparisons/${comparisonId}`, { replace: true });
    },
    [navigate],
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.createCompare({
        run_ids: initialRuns,
        mode,
        judge: judge.trim(),
      });
      setJobId(response.job_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Compare failed");
      setSubmitting(false);
    }
  }

  if (initialRuns.length < 2) {
    return (
      <div className="page-state page-state--error">
        Select at least two runs from <Link to="/runs">Runs</Link> to compare.
      </div>
    );
  }

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to="/runs">Runs</Link> / Compare
        </p>
        <h1>Compare runs</h1>
        <p className="page-header__subtitle">
          {selectedRuns[0]?.benchmark?.id ?? "—"} · {initialRuns.length} runs
        </p>
      </header>

      {jobId ? (
        <CompareProgress jobId={jobId} onFinished={handleFinished} />
      ) : (
        <form className="run-launcher" onSubmit={(event) => void handleSubmit(event)}>
          <ul className="compare-run-list">
            {selectedRuns.map((run) => (
              <li key={run.run_id}>
                <code>{run.run_id}</code> · {run.model}
              </li>
            ))}
          </ul>

          <label className="form-field">
            <span className="form-field__label">Mode</span>
            <select
              className="form-field__input"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
            >
              <option value="pairwise" disabled={initialRuns.length !== 2}>
                Pairwise (2 runs)
              </option>
              <option value="rubric">Rubric (2+ runs)</option>
            </select>
          </label>

          <label className="form-field">
            <span className="form-field__label">Judge model</span>
            <input
              className="form-field__input"
              type="text"
              placeholder="provider/model"
              value={judge}
              onChange={(event) => setJudge(event.target.value)}
            />
          </label>

          {error && <div className="run-launcher__error">{error}</div>}

          <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
            {submitting ? "Starting…" : "Run comparison"}
          </button>
        </form>
      )}
    </>
  );
}
