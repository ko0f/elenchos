import type { RunSummary } from "../api/types";

export function benchmarkIdForRuns(
  runIds: string[],
  runs: RunSummary[],
): string | null {
  const selected = runs.filter((run) => runIds.includes(run.run_id));
  if (selected.length === 0) {
    return null;
  }
  const ids = new Set(selected.map((run) => run.benchmark?.id ?? null));
  if (ids.size !== 1) {
    return null;
  }
  return [...ids][0];
}

export function canCompareRuns(runIds: string[], runs: RunSummary[]): boolean {
  if (runIds.length < 2) {
    return false;
  }
  return benchmarkIdForRuns(runIds, runs) !== null;
}

export function canBuildLeaderboard(runIds: string[], runs: RunSummary[]): boolean {
  if (runIds.length < 1) {
    return false;
  }
  return benchmarkIdForRuns(runIds, runs) !== null;
}
