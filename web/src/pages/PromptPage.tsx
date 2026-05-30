import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { ProviderModelSelect, qualifiedModel } from "../components/ProviderModelSelect";
import "../components/RunLauncher.css";
import "./PromptPage.css";

export function PromptPage() {
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    runId: string;
    output: string | null;
    latencyMs: number;
    error: string | null;
  } | null>(null);

  const { data: providers = [] } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: api.listProviders,
  });

  const qualified = qualifiedModel(provider, model);
  const canSubmit = Boolean(qualified) && text.trim().length > 0 && !submitting;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.prompt({ model: qualified, text: text.trim() });
      setResult({
        runId: response.run_id,
        output: response.output ?? null,
        latencyMs: response.latency_ms,
        error: response.error ?? null,
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Prompt failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <h1>Quick prompt</h1>
        <p className="page-header__subtitle">
          Send a one-off prompt to a model. Result is saved as a run.
        </p>
      </header>

      <form className="run-launcher" onSubmit={(event) => void handleSubmit(event)}>
        <ProviderModelSelect
          provider={provider}
          model={model}
          onProviderChange={setProvider}
          onModelChange={setModel}
          providers={providers}
          disabled={submitting}
        />

        <label className="form-field">
          <span className="form-field__label">Prompt</span>
          <textarea
            className="form-field__input prompt-textarea"
            rows={5}
            value={text}
            disabled={submitting}
            onChange={(event) => setText(event.target.value)}
            placeholder="Say hello in one word."
          />
        </label>

        {error && <div className="run-launcher__error">{error}</div>}

        <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
          {submitting ? "Sending…" : "Send prompt"}
        </button>
      </form>

      {result && (
        <div className="prompt-result">
          <div className="prompt-result__meta">
            <span>{Math.round(result.latencyMs)} ms</span>
            <Link to={`/runs/${result.runId}`}>View run {result.runId}</Link>
          </div>
          {result.error ? (
            <div className="run-launcher__error">{result.error}</div>
          ) : (
            <pre className="prompt-result__output">{result.output ?? "(empty)"}</pre>
          )}
        </div>
      )}
    </>
  );
}
