import { Link } from "react-router-dom";
import type { SuiteSummary } from "../api/types";
import "./SuiteCard.css";

interface SuiteCardProps {
  suite: SuiteSummary;
}

export function SuiteCard({ suite }: SuiteCardProps) {
  const sourceClass =
    suite.source === "builtin" ? "chip--source-builtin" : "chip--source-user";

  return (
    <Link to={`/benchmarks/${suite.id}`} className="suite-card">
      <div className="suite-card__header">
        <span className="suite-card__id">{suite.id}</span>
        <span className="suite-card__meta">
          v{suite.version} · {suite.task_count} task{suite.task_count === 1 ? "" : "s"}
        </span>
      </div>
      <p className="suite-card__description">{suite.description}</p>
      <div className="suite-card__footer">
        <span className={`chip chip--type`}>{suite.type}</span>
        <span className={`chip ${sourceClass}`}>{suite.source}</span>
      </div>
    </Link>
  );
}
