import { Fragment, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { useJobStream } from "../hooks/useJobStream";
import type { TaskDoneData, TaskResult } from "../api/types";
import { ScoreBadge } from "./ScoreBadge";
import { TaskOutputPanel } from "./TaskOutputPanel";
import "./RunProgress.css";

interface RunProgressProps {
  jobId: string;
  onFinished: (runId: string) => void;
}

function taskResultFromEvent(data: TaskDoneData): TaskResult {
  return {
    task_id: data.task_id,
    latency_ms: 0,
    score: data.score,
    error: data.error,
  };
}

export function RunProgress({ jobId, onFinished }: RunProgressProps) {
  const { events, status, runId, summary, error } = useJobStream(jobId);
  const [expanded, setExpanded] = useState<string | null>(null);

  const taskEvents = events.filter((item) => item.event === "task_done");
  const isLive =
    status === "streaming" || status === "polling" || status === "connecting";

  const { data: runDetail } = useQuery({
    queryKey: queryKeys.run(runId ?? ""),
    queryFn: () => api.getRun(runId!),
    enabled: Boolean(runId) && taskEvents.length > 0,
    refetchInterval: isLive ? 2000 : false,
  });

  const toggle = (taskId: string) => {
    setExpanded((current) => (current === taskId ? null : taskId));
  };
  const total =
    taskEvents.length > 0
      ? (taskEvents[taskEvents.length - 1]?.data.total as number | undefined)
      : undefined;
  const completed = taskEvents.length;
  const progressPct = total ? Math.round((completed / total) * 100) : 0;

  useEffect(() => {
    if (status === "done" && runId) {
      onFinished(runId);
    }
  }, [status, runId, onFinished]);

  return (
    <div className="run-progress">
      <div className="run-progress__header">
        <h2>Running benchmark</h2>
        <span className="run-progress__status">
          {status === "streaming" && "Live"}
          {status === "polling" && "Polling"}
          {status === "connecting" && "Connecting…"}
          {status === "done" && "Complete"}
          {status === "error" && "Error"}
        </span>
      </div>

      {total != null && (
        <div className="run-progress__bar-wrap">
          <div className="run-progress__bar" style={{ width: `${progressPct}%` }} />
        </div>
      )}

      {total != null && (
        <p className="run-progress__count">
          {completed} / {total} tasks
        </p>
      )}

      {runId && (
        <p className="run-progress__run-id">
          Run ID: <code>{runId}</code>
        </p>
      )}

      {error && <div className="run-progress__error">{error}</div>}

      {taskEvents.length > 0 && (
        <table className="run-progress__table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Score</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {taskEvents.map((item) => {
              const data = item.data as unknown as TaskDoneData;
              const isOpen = expanded === data.task_id;
              const result =
                runDetail?.results.find((row) => row.task_id === data.task_id) ??
                taskResultFromEvent(data);
              return (
                <Fragment key={`${data.task_id}-${data.index}`}>
                  <tr>
                    <td>{data.task_id}</td>
                    <td>
                      <ScoreBadge score={data.score} />
                    </td>
                    <td>
                      {data.error ? (
                        <span className="run-progress__task-error">{data.error}</span>
                      ) : (
                        "Done"
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="run-progress__expand"
                        onClick={() => toggle(data.task_id)}
                        aria-expanded={isOpen}
                      >
                        {isOpen ? "Hide" : "Show"}
                      </button>
                    </td>
                  </tr>
                  {isOpen && runId && (
                    <tr className="run-progress__detail-row">
                      <td colSpan={4}>
                        <div className="run-progress__detail">
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
      )}

      {status === "done" && summary && (
        <p className="run-progress__summary">Run finished — redirecting to results…</p>
      )}
    </div>
  );
}
