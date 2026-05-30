import { Fragment, useState } from "react";
import type { TaskResult } from "../api/types";
import { formatLatency } from "../lib/format";
import { ScoreBadge } from "./ScoreBadge";
import { TaskOutputPanel } from "./TaskOutputPanel";
import "./ResultsTable.css";

interface ResultsTableProps {
  runId: string;
  results: TaskResult[];
}

export function ResultsTable({ runId, results }: ResultsTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

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
          <th>Status</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {results.map((result) => {
          const isOpen = expanded === result.task_id;
          return (
            <Fragment key={result.task_id}>
              <tr>
                <td className="results-table__task">{result.task_id}</td>
                <td>
                  <ScoreBadge score={result.error ? null : result.score} />
                </td>
                <td>{formatLatency(result.latency_ms)}</td>
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
                <td>
                  <button
                    type="button"
                    className="results-table__expand"
                    onClick={() => toggle(result.task_id)}
                    aria-expanded={isOpen}
                  >
                    {isOpen ? "Hide" : "Show"}
                  </button>
                </td>
              </tr>
              {isOpen && (
                <tr className="results-table__detail-row">
                  <td colSpan={5}>
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
