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
  return `${Math.round(ms).toLocaleString()} ms`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) {
    return "—";
  }
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

export function runDurationMs(
  startedAt: string | null | undefined,
  finishedAt?: string | null,
  nowMs: number = Date.now(),
): number | null {
  if (!startedAt) {
    return null;
  }
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) {
    return null;
  }
  const end = finishedAt ? Date.parse(finishedAt) : nowMs;
  if (Number.isNaN(end)) {
    return null;
  }
  const ms = end - start;
  return ms >= 0 ? ms : null;
}

export function formatTokens(
  promptTokens: number | null | undefined,
  completionTokens: number | null | undefined,
): string {
  if (promptTokens == null && completionTokens == null) {
    return "—";
  }
  const total = (promptTokens ?? 0) + (completionTokens ?? 0);
  return total.toLocaleString();
}

export function formatTokenBreakdown(
  promptTokens: number | null | undefined,
  completionTokens: number | null | undefined,
): string | undefined {
  if (promptTokens == null && completionTokens == null) {
    return undefined;
  }
  const parts: string[] = [];
  if (promptTokens != null) {
    parts.push(`Prompt: ${promptTokens.toLocaleString()}`);
  }
  if (completionTokens != null) {
    parts.push(`Completion: ${completionTokens.toLocaleString()}`);
  }
  return parts.join(", ");
}

export function maxContextTokens(
  params: Record<string, unknown> | null | undefined,
): number | null {
  const value = params?.max_tokens;
  return typeof value === "number" && value > 0 ? value : null;
}

export function formatContextWindow(
  promptTokens: number | null | undefined,
  completionTokens: number | null | undefined,
  maxContextTokens: number | null | undefined,
): string {
  if (promptTokens == null && completionTokens == null) {
    return "—";
  }
  const used = (promptTokens ?? 0) + (completionTokens ?? 0);
  const usedLabel = used.toLocaleString();
  if (maxContextTokens == null) {
    return usedLabel;
  }
  return `${usedLabel} / ${maxContextTokens.toLocaleString()}`;
}

export function formatContextWindowTitle(
  promptTokens: number | null | undefined,
  completionTokens: number | null | undefined,
  maxContextTokens: number | null | undefined,
): string | undefined {
  const breakdown = formatTokenBreakdown(promptTokens, completionTokens);
  if (maxContextTokens == null) {
    return breakdown;
  }
  const parts: string[] = [];
  if (breakdown) {
    parts.push(breakdown);
  }
  parts.push(`Max context: ${maxContextTokens.toLocaleString()} tokens`);
  return parts.join(" · ");
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  return new Date(iso).toLocaleString();
}

export function baselineScoreVariant(
  score: number | null | undefined,
): "pass" | "fail" | "none" {
  if (score == null) {
    return "none";
  }
  if (score > 1) {
    return "pass";
  }
  if (score < 1) {
    return "fail";
  }
  return "none";
}

export function formatBaselineScore(score: number | null | undefined): string {
  if (score == null) {
    return "—";
  }
  return `${score.toFixed(2)}×`;
}

export function formatDelta(delta: number): string {
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(2)}`;
}

export function deltaVariant(delta: number): "pass" | "fail" | "none" {
  if (delta > 0) {
    return "pass";
  }
  if (delta < 0) {
    return "fail";
  }
  return "none";
}

export function meanScore(summary: Record<string, unknown> | null | undefined): number | null {
  if (!summary || typeof summary.mean_score !== "number") {
    return null;
  }
  return summary.mean_score;
}
