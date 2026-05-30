import type { Task } from "../api/types";
import "./SuiteTaskPanel.css";

interface SuiteTaskPanelProps {
  task: Task;
}

export function SuiteTaskPanel({ task }: SuiteTaskPanelProps) {
  return (
    <article className="task-panel">
      <header className="task-panel__header">
        <span className="task-panel__id">{task.id}</span>
        <span className="task-panel__type">{task.type}</span>
      </header>
      {task.description ? (
        <p className="task-panel__description">{task.description}</p>
      ) : null}
      <pre className="task-panel__prompt">{task.prompt}</pre>
      <div className="task-panel__scorers">
        {task.scorers.map((scorer) => (
          <span key={scorer} className={`scorer-chip scorer-chip--${scorer}`}>
            {scorer}
          </span>
        ))}
      </div>
    </article>
  );
}
