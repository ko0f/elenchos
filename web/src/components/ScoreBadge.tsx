import { formatScore, scoreVariant } from "../lib/format";
import "./ScoreBadge.css";

interface ScoreBadgeProps {
  score: number | null | undefined;
}

export function ScoreBadge({ score }: ScoreBadgeProps) {
  const variant = scoreVariant(score);
  return (
    <span className={`score-badge score-badge--${variant}`}>
      {formatScore(score)}
    </span>
  );
}
