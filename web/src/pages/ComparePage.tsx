import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { CompareProgress } from "../components/CompareProgress";
import { ProviderModelSelect, qualifiedModel } from "../components/ProviderModelSelect";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { canCompareRuns } from "../lib/runs";
import "../components/RunLauncher.css";
import "./ComparePage.css";

const COMPARE_PREFS_KEY = "elenchos.compare.prefs";

interface ComparePrefs {
  mode: string;
  judgeProvider: string;
  judgeModel: string;
  judgeEffort: string;
}

export function ComparePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialRuns = useMemo(
    () => searchParams.get("runs")?.split(",").filter(Boolean) ?? [],
    [searchParams],
  );
  const defaultMode = initialRuns.length === 2 ? "pairwise" : "rubric";
  const [prefs, setPrefs] = useLocalStorageState<ComparePrefs>(COMPARE_PREFS_KEY, {
    mode: defaultMode,
    judgeProvider: "",
    judgeModel: "",
    judgeEffort: "",
  });
  const mode =
    prefs.mode === "pairwise" && initialRuns.length !== 2 ? "rubric" : prefs.mode;
  const { judgeProvider, judgeModel, judgeEffort } = prefs;
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updatePrefs = useCallback(
    (patch: Partial<ComparePrefs>) => {
      setPrefs((current) => ({ ...current, ...patch }));
    },
    [setPrefs],
  );

  const { data: runs = [] } = useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.listRuns,
  });

  const { data: providers = [] } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: api.listProviders,
  });

  const judge = qualifiedModel(judgeProvider, judgeModel);
  const selectedRuns = runs.filter((run) => initialRuns.includes(run.run_id));
  const compareValid = canCompareRuns(initialRuns, runs);
  const canSubmit =
    initialRuns.length >= 2 &&
    compareValid &&
    Boolean(judge) &&
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
        judge,
        ...(judgeEffort
          ? { judge_effort: judgeEffort as "low" | "medium" | "high" }
          : {}),
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

  if (!compareValid) {
    return (
      <div className="page-state page-state--error">
        Compare needs 2+ runs from the same benchmark.{" "}
        <Link to="/runs">Back to Runs</Link>
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
              onChange={(event) => updatePrefs({ mode: event.target.value })}
            >
              <option value="pairwise" disabled={initialRuns.length !== 2}>
                Pairwise (2 runs)
              </option>
              <option value="rubric">Rubric (2+ runs)</option>
            </select>
          </label>

          <ProviderModelSelect
            provider={judgeProvider}
            model={judgeModel}
            onProviderChange={(value) => updatePrefs({ judgeProvider: value, judgeModel: "" })}
            onModelChange={(value) => updatePrefs({ judgeModel: value })}
            providers={providers}
            disabled={submitting}
          />

          <label className="form-field">
            <span className="form-field__label">Effort level</span>
            <select
              className="form-field__input"
              value={judgeEffort}
              disabled={submitting}
              onChange={(event) => updatePrefs({ judgeEffort: event.target.value })}
            >
              <option value="">Default</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
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
