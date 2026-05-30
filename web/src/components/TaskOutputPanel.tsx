import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { TaskResult } from "../api/types";
import { formatLatency } from "../lib/format";
import { parseModelOutput } from "../lib/modelOutput";
import "./TaskOutputPanel.css";

interface TaskOutputPanelProps {
  runId: string;
  result: TaskResult;
  pending?: boolean;
}

const REASONING_PREVIEW_LINES = 4;

function OutputSection({ title, text }: { title: string; text: string }) {
  return (
    <section>
      <h4 className="output-panel__section-title">{title}</h4>
      <pre className="output-panel__block">{text}</pre>
    </section>
  );
}

function CollapsibleOutputSection({ title, text }: { title: string; text: string }) {
  const [expanded, setExpanded] = useState(false);
  const lines = text.split("\n");
  const collapsible = lines.length > REASONING_PREVIEW_LINES;
  const displayText =
    collapsible && !expanded
      ? `${lines.slice(0, REASONING_PREVIEW_LINES).join("\n")}\n…`
      : text;

  return (
    <section>
      <div className="output-panel__section-header">
        <h4 className="output-panel__section-title">{title}</h4>
        {collapsible && (
          <button
            type="button"
            className="output-panel__expand"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
          >
            {expanded ? "Show less" : "Show all"}
          </button>
        )}
      </div>
      <pre className="output-panel__block">{displayText}</pre>
    </section>
  );
}

export function TaskOutputPanel({ runId, result, pending = false }: TaskOutputPanelProps) {
  const inlineOutput = result.output ?? null;
  const { data: fetchedOutput, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.taskOutput(runId, result.task_id),
    queryFn: () => api.getTaskOutput(runId, result.task_id),
    enabled: !pending && !result.error && inlineOutput == null,
  });
  const output = inlineOutput ?? fetchedOutput ?? null;
  const parsed = output != null ? parseModelOutput(output) : null;

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
      ) : pending || isLoading ? (
        <p className="output-panel__loading">Waiting for model response…</p>
      ) : isError ? (
        <p className="output-panel__error">
          {error instanceof Error ? error.message : "Failed to load output"}
        </p>
      ) : parsed?.reasoning ? (
        <>
          <CollapsibleOutputSection title="Reasoning" text={parsed.reasoning} />
          {parsed.answer ? (
            <OutputSection title="Output" text={parsed.answer} />
          ) : (
            <p className="output-panel__loading">
              No final answer yet
              {result.finish_reason === "length" ? " (hit token limit)" : ""}.
            </p>
          )}
        </>
      ) : parsed?.answer ? (
        <OutputSection title="Output" text={parsed.answer} />
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
