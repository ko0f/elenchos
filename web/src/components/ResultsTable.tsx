import { Fragment, useState } from "react";
import type { TaskResult } from "../api/types";
import {
  formatContextWindow,
  formatContextWindowTitle,
  formatLatency,
  formatTokenBreakdown,
  formatTokens,
  maxContextTokens,
} from "../lib/format";
import { ScoreBadge } from "./ScoreBadge";
import { TaskOutputPanel } from "./TaskOutputPanel";
import "./ResultsTable.css";

interface ResultsTableProps {
  runId: string;
  results: TaskResult[];
  runParams?: Record<string, unknown> | null;
}

export function ResultsTable({ runId, results, runParams }: ResultsTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const contextLimit = maxContextTokens(runParams);

  const toggle = (taskId: string) => {
    setExpanded((current) => (current === taskId ? null : taskId));
  };

  return (
    <table className="results-table">
      <thead>
        <tr>
          <th>Task</th>
          <th>Score</th>
          <th>Latency</th>
          <th>Tokens</th>
          <th>Context</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {results.map((result) => {
          const isOpen = expanded === result.task_id;
          return (
            <Fragment key={result.task_id}>
              <tr
                className="results-table__row"
                onClick={() => toggle(result.task_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    toggle(result.task_id);
                  }
                }}
                tabIndex={0}
                aria-expanded={isOpen}
              >
                <td className="results-table__task">{result.task_id}</td>
                <td>
                  <ScoreBadge score={result.error ? null : result.score} />
                </td>
                <td>{formatLatency(result.latency_ms)}</td>
                <td
                  className="results-table__tokens"
                  title={formatTokenBreakdown(result.prompt_tokens, result.completion_tokens)}
                >
                  {formatTokens(result.prompt_tokens, result.completion_tokens)}
                </td>
                <td
                  className="results-table__tokens"
                  title={formatContextWindowTitle(
                    result.prompt_tokens,
                    result.completion_tokens,
                    contextLimit,
                  )}
                >
                  {formatContextWindow(
                    result.prompt_tokens,
                    result.completion_tokens,
                    contextLimit,
                  )}
                </td>
                <td>
                  {result.error ? (
                    <span className="results-table__error">error</span>
                  ) : result.score != null && result.score >= 1.0 ? (
                    "pass"
                  ) : result.score != null && result.score > 0 ? (
                    "partial"
                  ) : result.score != null ? (
                    "fail"
                  ) : (
                    "unscored"
                  )}
                </td>
              </tr>
              {isOpen && (
                <tr className="results-table__detail-row">
                  <td colSpan={6}>
                    <div className="results-table__detail">
                      <TaskOutputPanel runId={runId} result={result} />
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
