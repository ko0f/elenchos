import { useEffect } from "react";
import { useJobStream } from "../hooks/useJobStream";
import type { TaskDoneData } from "../api/types";
import { ScoreBadge } from "./ScoreBadge";
import "./RunProgress.css";

interface RunProgressProps {
  jobId: string;
  onFinished: (runId: string) => void;
}

export function RunProgress({ jobId, onFinished }: RunProgressProps) {
  const { events, status, runId, summary, error } = useJobStream(jobId);

  const taskEvents = events.filter((item) => item.event === "task_done");
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
            </tr>
          </thead>
          <tbody>
            {taskEvents.map((item) => {
              const data = item.data as unknown as TaskDoneData;
              return (
                <tr key={`${data.task_id}-${data.index}`}>
                  <td>{data.task_id}</td>
                  <td>
                    <ScoreBadge score={data.score} />
                  </td>
                  <td>{data.error ? <span className="run-progress__task-error">{data.error}</span> : "Done"}</td>
                </tr>
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
