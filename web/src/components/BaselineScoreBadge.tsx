import {
  baselineScoreVariant,
  formatBaselineScore,
} from "../lib/format";
import "./BaselineScoreBadge.css";

interface BaselineScoreBadgeProps {
  score: number | null | undefined;
  isBaseline?: boolean;
}

export function BaselineScoreBadge({ score, isBaseline }: BaselineScoreBadgeProps) {
  if (isBaseline) {
    return <span className="baseline-score-badge baseline-score-badge--baseline">baseline</span>;
  }
  const variant = baselineScoreVariant(score);
  return (
    <span className={`baseline-score-badge baseline-score-badge--${variant}`}>
      {formatBaselineScore(score)}
    </span>
  );
}
