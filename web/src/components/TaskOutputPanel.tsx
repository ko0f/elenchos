import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { TaskResult } from "../api/types";
import { formatLatency } from "../lib/format";
import "./TaskOutputPanel.css";

interface TaskOutputPanelProps {
  runId: string;
  result: TaskResult;
}

export function TaskOutputPanel({ runId, result }: TaskOutputPanelProps) {
  const { data: output, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.taskOutput(runId, result.task_id),
    queryFn: () => api.getTaskOutput(runId, result.task_id),
    enabled: !result.error,
  });

  return (
    <div className="output-panel">
      {result.prompt && (
        <section>
          <h4 className="output-panel__section-title">Prompt</h4>
          <pre className="output-panel__block">{result.prompt}</pre>
        </section>
      )}

      {result.error ? (
        <p className="output-panel__error">{result.error}</p>
      ) : isLoading ? (
        <p className="output-panel__loading">Loading output…</p>
      ) : isError ? (
        <p className="output-panel__error">
          {error instanceof Error ? error.message : "Failed to load output"}
        </p>
      ) : output ? (
        <section>
          <h4 className="output-panel__section-title">Output</h4>
          <pre className="output-panel__block">{output}</pre>
        </section>
      ) : (
        <p className="output-panel__loading">No output</p>
      )}

      <div className="output-panel__metrics">
        <span>Latency: {formatLatency(result.latency_ms)}</span>
        {result.prompt_tokens != null && (
          <span>Prompt tokens: {result.prompt_tokens}</span>
        )}
        {result.completion_tokens != null && (
          <span>Completion tokens: {result.completion_tokens}</span>
        )}
        {result.finish_reason && <span>Finish: {result.finish_reason}</span>}
        {result.scorer && <span>Scorer: {result.scorer}</span>}
        {result.passed != null && result.total != null && (
          <span>
            Tests: {result.passed}/{result.total}
          </span>
        )}
      </div>
    </div>
  );
}
