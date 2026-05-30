# Plan — Baseline runs & baseline-relative comparison

Revamp comparison around a per-benchmark **baseline run**. Every other run of the
same benchmark gets a **relative score** vs that baseline: `1.0` = parity,
`< 1` = worse, `> 1` = better. Scores are persisted to file storage, shown next
to each run in the Runs table, and broken down per task in the run drilldown.

## Key insight

Each run already persists a per-task `score` in `results.jsonl` (deterministic
*and* `judge_rubric` scorers run during the run — see `runner._run_task` →
`score_task_output`), plus `run.summary.mean_score`. So the baseline-relative
score is **pure arithmetic over stored scores — no judge call, no job queue**.
Computation is cheap and synchronous.

The existing judge-based `compare` / `comparisons/` / leaderboard flow is left
intact; this feature is additive. See [Open questions](#open-questions) re:
deprecating the manual 2-run compare.

## Scoring model

Given a candidate run C and the baseline run B for the same benchmark:

- **Shared tasks** = tasks present in both, with `error is None` and
  `score is not None` in both.
- **Per task**: `baseline_score`, `score` (candidate), `delta = score − baseline_score`.
- **Relative score** = `Σ candidate_score / Σ baseline_score` over shared tasks
  (ratio of sums = ratio of means; avoids per-task divide-by-zero).

Edge cases:

| Case | Result |
|---|---|
| C *is* the baseline | `relative_score = 1.0`, flagged `is_baseline` |
| No baseline set for benchmark | `null` (no comparison) |
| No shared scored tasks | `null` |
| `Σ baseline_score == 0` | `null` (baseline scored zero everywhere → undefined) |

Display: `>1` green, `<1` red, `==1` neutral. Format as e.g. `1.12×`.

## Storage layer (`src/elenchos/storage.py`)

### Baseline pointer — `<data_dir>/baselines.json`

One baseline per benchmark:

```json
{ "coding-basics": "a1b2c3", "text-reasoning": "d4e5f6" }
```

New helpers:

- `load_baselines(settings) -> dict[str, str]`
- `get_baseline_run_id(benchmark_id, settings) -> str | None`
- `set_baseline(benchmark_id, run_id, settings)` — validate the run exists and
  its `benchmark.id == benchmark_id`; write atomically (temp + replace, like
  `rewrite_results`).
- `clear_baseline(benchmark_id, settings)`

Update `delete_run`: if the deleted run is a baseline, drop its entry from
`baselines.json` (dependent cached scores then read as stale → recomputed).

### Cached relative score — `<run_dir>/baseline_score.json`

Persists the comparison the user asked to store on disk:

```json
{
  "baseline_run_id": "a1b2c3",
  "relative_score": 1.12,
  "computed_at": "2026-05-30T14:05:40Z",
  "tasks": [
    { "task_id": "fizzbuzz", "baseline_score": 1.0, "score": 1.0, "delta": 0.0 }
  ]
}
```

Helpers: `write_baseline_score(run_dir, payload)`, `read_baseline_score(run_dir) -> dict | None`.

Cache is **valid** when its `baseline_run_id` equals the current baseline for the
run's benchmark; otherwise recompute and rewrite. (Cheap to recompute, so the
file is a convenience/snapshot cache, not the source of truth.)

## Comparison logic (new `src/elenchos/baseline.py`)

```python
@dataclass
class BaselineTask:
    task_id: str
    baseline_score: float
    score: float
    delta: float

@dataclass
class BaselineComparison:
    baseline_run_id: str
    baseline_model: str
    relative_score: float | None
    is_baseline: bool
    tasks: list[BaselineTask]
    computed_at: str
```

- `compute_baseline_comparison(run_id, settings) -> BaselineComparison | None`
  1. Resolve candidate run + `benchmark.id`.
  2. `baseline_run_id = get_baseline_run_id(benchmark_id)`; `None` → return `None`.
  3. If `run_id == baseline_run_id` → `relative_score=1.0, is_baseline=True, tasks=[]`.
  4. Load both runs' results (`include_output=False`), intersect shared scored
     tasks, build `tasks`, compute `relative_score` per the [scoring model](#scoring-model).
- `get_or_compute_baseline_comparison(run_id, settings)` — read cache; if missing
  or stale, compute + `write_baseline_score`. Used by the API.

## Web API

### Routers (`src/elenchos/web/routers/runs.py`)

- `POST /runs/{run_id}/baseline` → set this run as baseline for its benchmark
  (404 if run missing, 400 if run has no benchmark). Returns the updated run summary.
- `DELETE /runs/{run_id}/baseline` → clear the baseline for that benchmark
  (only if this run is the current baseline). 204.
- Extend `GET /runs/{run_id}` to attach `baseline_comparison`.

### Schemas (`src/elenchos/web/schemas.py`)

- `RunSummaryResponse`: add `is_baseline: bool = False`,
  `baseline_score: float | None = None`, `baseline_run_id: str | None = None`.
  Populate in `list_runs_endpoint` via `get_or_compute_baseline_comparison`
  (per run; the disk cache keeps this fast).
- New `BaselineTaskResponse` and `BaselineComparisonResponse`; add
  `baseline_comparison: BaselineComparisonResponse | None` to `RunDetailResponse`.
- Mapper `baseline_comparison_from_domain(...)`.

`run_summary_from_domain` gains a `comparison` arg (or a wrapper builds the
summary with baseline fields).

## Frontend

### API layer

- `web/src/api/types.ts`: extend `RunSummary` (`is_baseline`, `baseline_score`,
  `baseline_run_id`); add `BaselineTask`, `BaselineComparison`; add
  `baseline_comparison?` to `RunDetail`.
- `web/src/api/client.ts`: `setBaseline(runId)`, `clearBaseline(runId)`;
  invalidate `queryKeys.runs` + `queryKeys.run(runId)` on success.

### Runs table (`web/src/pages/RunsPage.tsx`)

- New **Baseline** column: a star toggle per row. Filled star = current baseline
  for that benchmark; click empty → `setBaseline`; click filled → `clearBaseline`.
  Setting a baseline is per-benchmark, so it swaps automatically (last write wins
  in `baselines.json`).
- New **vs Baseline** column: relative score badge.
  - baseline row → `baseline` chip
  - has score → `1.12×`, colored (`>1` green / `<1` red / `=1` neutral)
  - no baseline / not comparable → `—`
- New `BaselineScoreBadge` component (mirror `ScoreBadge`).
- Reorient the page: the inline baseline column replaces "Compare selected" as the
  primary comparison affordance. Keep the **Leaderboard** link. (Multi-select +
  `/compare` — see Open questions.)

### Run drilldown (`web/src/pages/RunDetailPage.tsx`)

- Below `<ResultsTable>`, render a new `<BaselineComparison>` section when
  `data.baseline_comparison` is present:
  - Header: link to baseline run + overall relative score badge.
  - Table: `Task | Baseline | This run | Δ` (colored delta).
  - If `is_baseline` → show a "This run is the baseline" note instead of the table.
- Optionally surface the relative score as a 5th `metric-card`.

## Tests

Python:

- `test_storage.py`: baseline set/get/clear, atomic write, `delete_run` clears
  baseline.
- `test_baseline.py` (new): parity (1.0), better (>1), worse (<1), zero-baseline
  → `None`, no shared tasks → `None`, candidate-is-baseline, cache hit vs stale
  recompute.
- `test_web_api.py`: `POST`/`DELETE /runs/{id}/baseline`; `baseline_score` in
  `GET /runs`; `baseline_comparison` in `GET /runs/{id}`; 400/404 paths.

Frontend:

- `RunsPage.test.tsx`: star toggle calls set/clear; badge renders score/baseline/—.
- `RunDetailPage.test.tsx`: baseline section renders rows + delta; baseline-run note.

## Rollout order

1. Storage helpers (`baselines.json`, `baseline_score.json`) + `delete_run` update.
2. `baseline.py` compute/cache logic + unit tests.
3. API endpoints + schema fields + mappers + API tests.
4. Frontend types/client.
5. RunsPage baseline column + badge.
6. RunDetailPage baseline breakdown.
7. Frontend tests; update `docs/design.md` storage layout if desired.

## Open questions

- **Manual 2-run compare**: keep the judge-based `/compare` + `ComparePage` as-is
  (additive baseline feature), or remove it now that baseline is the primary
  comparison? Plan assumes *keep*; removal is a follow-up.
- **Judge in baseline scoring**: not needed — stored per-task scores already
  cover deterministic and rubric suites. Only revisit if we want a qualitative
  rationale per task in the baseline breakdown.
- **`GET /runs` cost**: recomputes stale caches inline. Fine for local-scale run
  counts; revisit (e.g. precompute on run finish / on baseline change) if slow.
