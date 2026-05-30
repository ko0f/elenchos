import { useEffect } from "react";
import { useJobStream } from "../hooks/useJobStream";
import "./RunProgress.css";

interface CompareProgressProps {
  jobId: string;
  onFinished: (comparisonId: string) => void;
}

export function CompareProgress({ jobId, onFinished }: CompareProgressProps) {
  const { events, status, comparisonId, error } = useJobStream(jobId);

  const taskEvents = events.filter((item) => item.event === "task_done");
  const total =
    taskEvents.length > 0
      ? (taskEvents[taskEvents.length - 1]?.data.total as number | undefined)
      : undefined;
  const completed = taskEvents.length;
  const progressPct = total ? Math.round((completed / total) * 100) : 0;

  useEffect(() => {
    if (status === "done" && comparisonId) {
      onFinished(comparisonId);
    }
  }, [status, comparisonId, onFinished]);

  return (
    <div className="run-progress">
      <div className="run-progress__header">
        <h2>Comparing runs</h2>
        <span className="run-progress__status">
          {status === "streaming" && "Live"}
          {status === "polling" && "Polling"}
          {status === "connecting" && "Connecting…"}
          {status === "done" && "Complete"}
          {status === "error" && "Error"}
        </span>
      </div>

      {total != null && (
        <>
          <div className="run-progress__bar-wrap">
            <div className="run-progress__bar" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="run-progress__count">
            {completed} / {total} tasks
          </p>
        </>
      )}

      {comparisonId && (
        <p className="run-progress__run-id">
          Comparison ID: <code>{comparisonId}</code>
        </p>
      )}

      {error && <div className="run-progress__error">{error}</div>}

      {taskEvents.length > 0 && (
        <table className="run-progress__table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Winner</th>
            </tr>
          </thead>
          <tbody>
            {taskEvents.map((item) => (
              <tr key={`${item.data.task_id}-${item.data.index}`}>
                <td>{String(item.data.task_id)}</td>
                <td className="mono">{String(item.data.winner_run_id ?? "tie")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {status === "done" && (
        <p className="run-progress__summary">Comparison finished — redirecting…</p>
      )}
    </div>
  );
}
