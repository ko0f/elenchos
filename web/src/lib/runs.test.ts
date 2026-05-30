import { describe, expect, it } from "vitest";
import type { RunSummary } from "../api/types";
import { canCompareRuns, canBuildLeaderboard } from "./runs";

const runs: RunSummary[] = [
  {
    run_id: "a",
    started_at: "2025-01-01T00:00:00Z",
    model: "ollama/a",
    benchmark: { id: "text-reasoning-v1", version: 1 },
  },
  {
    run_id: "b",
    started_at: "2025-01-01T01:00:00Z",
    model: "ollama/b",
    benchmark: { id: "text-reasoning-v1", version: 1 },
  },
  {
    run_id: "c",
    started_at: "2025-01-01T02:00:00Z",
    model: "ollama/c",
    benchmark: { id: "coding-basics-v1", version: 1 },
  },
];

describe("run selection helpers", () => {
  it("allows compare for two same-benchmark runs", () => {
    expect(canCompareRuns(["a", "b"], runs)).toBe(true);
  });

  it("blocks compare for mixed benchmarks", () => {
    expect(canCompareRuns(["a", "c"], runs)).toBe(false);
  });

  it("blocks compare for fewer than two runs", () => {
    expect(canCompareRuns(["a"], runs)).toBe(false);
  });

  it("allows leaderboard for one or more same-benchmark runs", () => {
    expect(canBuildLeaderboard(["a"], runs)).toBe(true);
    expect(canBuildLeaderboard(["a", "b"], runs)).toBe(true);
    expect(canBuildLeaderboard(["a", "c"], runs)).toBe(false);
  });
});
