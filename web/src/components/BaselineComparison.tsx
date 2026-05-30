import { Link } from "react-router-dom";
import type { BaselineComparison as BaselineComparisonData } from "../api/types";
import { deltaVariant, formatDelta, formatScore } from "../lib/format";
import { BaselineScoreBadge } from "./BaselineScoreBadge";
import "./BaselineComparison.css";

interface BaselineComparisonProps {
  comparison: BaselineComparisonData;
}

export function BaselineComparison({ comparison }: BaselineComparisonProps) {
  if (comparison.is_baseline) {
    return (
      <section className="baseline-comparison">
        <h2 className="baseline-comparison__title">Baseline comparison</h2>
        <p className="baseline-comparison__note">This run is the baseline.</p>
      </section>
    );
  }

  return (
    <section className="baseline-comparison">
      <div className="baseline-comparison__header">
        <h2 className="baseline-comparison__title">Baseline comparison</h2>
        <p className="baseline-comparison__meta">
          vs{" "}
          <Link to={`/runs/${comparison.baseline_run_id}`}>
            {comparison.baseline_run_id}
          </Link>{" "}
          ({comparison.baseline_model})
        </p>
        <BaselineScoreBadge score={comparison.relative_score} />
      </div>
      {comparison.tasks.length > 0 ? (
        <table className="baseline-comparison__table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Baseline</th>
              <th>This run</th>
              <th>Δ</th>
            </tr>
          </thead>
          <tbody>
            {comparison.tasks.map((task) => (
              <tr key={task.task_id}>
                <td>{task.task_id}</td>
                <td>{formatScore(task.baseline_score)}</td>
                <td>{formatScore(task.score)}</td>
                <td>
                  <span
                    className={`baseline-comparison__delta baseline-comparison__delta--${deltaVariant(task.delta)}`}
                  >
                    {formatDelta(task.delta)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="baseline-comparison__note">No shared scored tasks to compare.</p>
      )}
    </section>
  );
}
