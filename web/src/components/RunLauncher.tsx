import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { SuiteDetail } from "../api/types";
import { DEFAULT_MAX_TOKENS } from "../lib/defaults";
import { ProviderModelSelect, qualifiedModel } from "./ProviderModelSelect";
import "./RunLauncher.css";

interface RunLauncherProps {
  suite: SuiteDetail;
  onLaunch: (runId: string) => void;
}

export function RunLauncher({ suite, onLaunch }: RunLauncherProps) {
  const defaults = suite.defaults?.params;
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState(String(defaults?.temperature ?? 0));
  const [maxTokens, setMaxTokens] = useState(
    String(defaults?.max_tokens ?? DEFAULT_MAX_TOKENS),
  );
  const [concurrency, setConcurrency] = useState("1");
  const [allowCodeExec, setAllowCodeExec] = useState(false);
  const [judge, setJudge] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: providers = [] } = useQuery({
    queryKey: queryKeys.providers,
    queryFn: api.listProviders,
  });

  const qualified = qualifiedModel(provider, model);
  const gatesOk =
    (!suite.requires_code_exec || allowCodeExec) &&
    (!suite.requires_judge || judge.trim().length > 0);
  const canSubmit = Boolean(qualified) && gatesOk && !submitting;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await api.createRun({
        benchmark: suite.id,
        model: qualified,
        temperature: Number(temperature),
        max_tokens: Number(maxTokens),
        concurrency: Number(concurrency),
        allow_code_exec: allowCodeExec,
        judge: judge.trim() || undefined,
      });
      if (!response.run_id) {
        setError("Run started but no run ID returned");
        setSubmitting(false);
        return;
      }
      onLaunch(response.run_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to start run");
      setSubmitting(false);
    }
  }

  return (
    <form className="run-launcher" onSubmit={(event) => void handleSubmit(event)}>
      <ProviderModelSelect
        provider={provider}
        model={model}
        onProviderChange={setProvider}
        onModelChange={setModel}
        providers={providers}
        disabled={submitting}
      />

      <div className="form-row">
        <label className="form-field">
          <span className="form-field__label">Temperature</span>
          <input
            className="form-field__input"
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            disabled={submitting}
            onChange={(event) => setTemperature(event.target.value)}
          />
        </label>

        <label className="form-field">
          <span className="form-field__label">Max tokens</span>
          <input
            className="form-field__input"
            type="number"
            min="1"
            value={maxTokens}
            disabled={submitting}
            onChange={(event) => setMaxTokens(event.target.value)}
          />
        </label>

        <label className="form-field">
          <span className="form-field__label">Concurrency</span>
          <input
            className="form-field__input"
            type="number"
            min="1"
            value={concurrency}
            disabled={submitting}
            onChange={(event) => setConcurrency(event.target.value)}
          />
        </label>
      </div>

      {suite.requires_code_exec && (
        <div className="run-launcher__gate run-launcher__gate--warn">
          <p className="run-launcher__gate-text">
            This suite executes model-generated code in a sandbox. Only enable if you trust
            the model output.
          </p>
          <label className="form-checkbox">
            <input
              type="checkbox"
              checked={allowCodeExec}
              disabled={submitting}
              onChange={(event) => setAllowCodeExec(event.target.checked)}
            />
            Allow code execution
          </label>
        </div>
      )}

      {suite.requires_judge && (
        <div className="run-launcher__gate run-launcher__gate--info">
          <label className="form-field">
            <span className="form-field__label">Judge model</span>
            <input
              className="form-field__input"
              type="text"
              placeholder="provider/model"
              value={judge}
              disabled={submitting}
              onChange={(event) => setJudge(event.target.value)}
            />
          </label>
        </div>
      )}

      {error && <div className="run-launcher__error">{error}</div>}

      <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
        {submitting ? "Starting…" : "Launch run"}
      </button>
    </form>
  );
}
