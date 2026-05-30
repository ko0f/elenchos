export function scoreVariant(score: number | null | undefined): "pass" | "partial" | "fail" | "none" {
  if (score == null) {
    return "none";
  }
  if (score >= 1.0) {
    return "pass";
  }
  if (score > 0) {
    return "partial";
  }
  return "fail";
}

export function formatScore(score: number | null | undefined): string {
  if (score == null) {
    return "—";
  }
  return score.toFixed(2);
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) {
    return "—";
  }
  return `${Math.round(ms)} ms`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  return new Date(iso).toLocaleString();
}

export function meanScore(summary: Record<string, unknown> | null | undefined): number | null {
  if (!summary || typeof summary.mean_score !== "number") {
    return null;
  }
  return summary.mean_score;
}
