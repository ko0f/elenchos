# Elenchos — Frontend + BFF Design

A local web UI for the Elenchos benchmark CLI. The UI lets a user **browse
benchmark suites (the test templates)**, **run them against a model**, and
**browse run results** (per-task outputs, scores, comparisons, leaderboards).

This document covers the **frontend (FE)** and the **backend-for-frontend
(BFF)** that sits between it and the existing Python domain code. It assumes the
core CLI design in [`design.md`](design.md) and the current implementation under
`src/elenchos/`.

## 1. Goals & Non-goals

### Goals

- **Browse templates**: list every suite the registry discovers (built-in +
  user) and inspect a suite's tasks — prompt, type, and configured scorers.
- **Run a suite**: pick a provider/model, set params (temperature, max tokens,
  concurrency), toggle code execution, choose a judge, and launch a run with
  **live progress**.
- **Browse results**: list past runs, open a run to see per-task prompt/output/
  score/latency/tokens, compare two runs (judge), and view a leaderboard.
- **Reuse, don't reimplement**: the BFF calls the existing domain modules
  in-process (`benchmarks`, `runner`, `storage`, `compare`, `reporter`,
  `providers`). No business logic is duplicated in JS.
- **Local-first**: binds to `127.0.0.1` by default; same machine, same data dir
  (`~/.elenchos/`) as the CLI. The CLI and UI are interchangeable views over
  the same files.

### Non-goals (v1)

- Multi-user / auth / hosting. This is a single-user local tool.
- Editing/authoring suite YAML in the browser (read-only for v1; author files
  on disk as today). A future phase may add an editor.
- Replacing the CLI. The UI is additive; the CLI remains the primary surface.
- Real-time collaboration or remote run orchestration.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (SPA)                            │
│  React + Vite + TS · TanStack Query · routes/screens         │
└───────────────────────────────┬─────────────────────────────┘
                                 │  JSON over HTTP + SSE (localhost)
┌───────────────────────────────▼─────────────────────────────┐
│                       BFF (FastAPI)                          │
│  src/elenchos/web/                                           │
│  • REST endpoints (thin, async)                             │
│  • Pydantic response models (DTOs)                          │
│  • JobManager (background runs) + SSE progress              │
└───────────────────────────────┬─────────────────────────────┘
                                 │  direct in-process calls
┌───────────────────────────────▼─────────────────────────────┐
│              Existing domain modules (unchanged)             │
│  benchmarks.registry · runner · storage · compare ·          │
│  reporter · providers.registry · config                     │
└───────────────────────────────┬─────────────────────────────┘
                                 │ read/write
                       ┌─────────▼─────────┐
                       │   ~/.elenchos/    │
                       │ runs/ comparisons/│
                       │ benchmarks/ config│
                       └───────────────────┘
```

The BFF is **not** a microservice tier — it's a thin HTTP adapter that imports
the same Python package the CLI uses. The CLI (`typer`) and the BFF (`fastapi`)
are two front doors onto one domain layer.

### Why a BFF (and not the FE calling provider APIs directly)

- The domain logic (suite resolution, scorer validation, run orchestration,
  resume, judge comparison, leaderboard aggregation) already lives in Python and
  is non-trivial. Re-expressing it in TypeScript would fork the logic.
- Provider API keys (`OPENROUTER_API_KEY`) must never reach the browser. All
  provider calls stay server-side.
- Code execution (`unit_test` scorer) and the filesystem store are inherently
  server-side concerns.

## 3. Tech Stack

### BFF

| Concern | Choice | Rationale |
|---|---|---|
| Web framework | **FastAPI** | Async, Pydantic-native (already a dep), OpenAPI for free. |
| ASGI server | **uvicorn** | Standard, lightweight. |
| Progress stream | **SSE** (`sse-starlette` or a plain `StreamingResponse`) | One-way server→client fits run progress; simpler than WebSockets. |
| DTOs | **Pydantic v2** | Already in use; response models double as the API schema. |

**New dependencies to add** (a `web` optional group so the core CLI stays lean):
`fastapi`, `uvicorn[standard]`, and optionally `sse-starlette`. These are not
yet in `pyproject.toml` — adding them needs sign-off (per repo conventions, ask
before installing). Proposed:

```toml
[project.optional-dependencies]
web = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "sse-starlette>=2.1"]
```

Launch via a new CLI command so the UI ships with the tool:

```
elenchos serve [--host 127.0.0.1] [--port 8765] [--open]
```

`serve` starts uvicorn, and in production serves the built FE static assets from
the same origin (no CORS needed in prod; CORS allowed for the Vite dev server).

### Frontend

| Concern | Choice | Rationale |
|---|---|---|
| Framework | **React + TypeScript** | Ubiquitous; good for the modest screen count. |
| Build | **Vite** | Fast dev server, simple static build. |
| Data fetching | **TanStack Query** | Caching, polling, and request states (loading/error) for free. |
| Routing | **React Router** | A handful of routes. |
| Styling | lightweight CSS (CSS Modules or Tailwind) + a small component set | Keep deps minimal; match the CLI's clean, table-dense aesthetic. |

A server-rendered **HTMX** alternative is viable (less JS, no build step) and
noted in Open Questions — but the live-progress and compare-selection
interactions are cleaner as a small SPA, so React is the default.

The FE lives in `web/` at the repo root (its own `package.json`); the build
output is emitted into `src/elenchos/web/static/` and packaged with the wheel so
`elenchos serve` works from an install.

## 4. BFF API Surface

All routes under `/api`. Each maps to an existing domain function — the BFF
mostly translates dataclasses ↔ Pydantic DTOs and handles HTTP concerns.

### 4.1 Providers & models

| Method | Path | Domain call | Returns |
|---|---|---|---|
| GET | `/api/providers` | `list_provider_names`, `get_provider().health_check()` | `[{name, base_url, healthy}]` |
| GET | `/api/providers/{name}/models` | `get_provider(name).list_models()` | `{models: [str]}` (404 unknown, 502 unhealthy) |

### 4.2 Benchmarks (templates)

| Method | Path | Domain call | Returns |
|---|---|---|---|
| GET | `/api/benchmarks` | `list_suite_summaries` | suite summaries (below) |
| GET | `/api/benchmarks/{id}` | `resolve_benchmark` | full suite detail (below) |

`GET /api/benchmarks` → from `SuiteSummary`:

```json
[{ "id": "coding-basics-v1", "version": 1, "type": "coding",
   "description": "…", "task_count": 5, "source": "builtin" }]
```

`GET /api/benchmarks/{id}` → from `BenchmarkSuite`, with derived run hints so the
FE can pre-validate the launcher:

```json
{
  "id": "coding-basics-v1", "version": 1, "type": "coding",
  "description": "…",
  "defaults": { "params": { "temperature": 0.0, "max_tokens": 1024 } },
  "tasks": [
    { "id": "fizzbuzz", "type": "coding", "prompt": "Write a Python…",
      "scorers": ["unit_test"] }
  ],
  "requires_code_exec": true,     // any task uses unit_test
  "requires_judge": false         // any task uses judge_rubric
}
```

`requires_code_exec` / `requires_judge` are computed in the BFF from
`suite.effective_scoring(task)` (mirroring `runner._validate_suite_for_run`), so
the launcher can require the matching toggles before allowing submit.

### 4.3 Runs

| Method | Path | Domain call | Notes |
|---|---|---|---|
| POST | `/api/runs` | `run_suite` (background) | start a run → `{job_id, run_id}` |
| GET | `/api/runs` | `list_runs` | run summaries |
| GET | `/api/runs/{run_id}` | `find_run` + `load_results` | run detail + per-task results |
| GET | `/api/runs/{run_id}/results/{task_id}/output` | `read_output` | raw output text (`text/plain`) |
| GET | `/api/jobs/{job_id}/events` | JobManager | **SSE** live progress |
| GET | `/api/jobs/{job_id}` | JobManager | poll job status (SSE fallback) |

`POST /api/runs` body (mirrors the `run` command options):

```json
{
  "benchmark": "coding-basics-v1",
  "model": "ollama/llama3.1:8b",
  "temperature": 0.0,            // optional override
  "max_tokens": 1024,           // optional override
  "concurrency": 4,             // optional
  "allow_code_exec": true,      // required if requires_code_exec
  "judge": "openrouter/anthropic/claude-sonnet-4-6"  // required if requires_judge
}
```

Validation errors (`SuiteRunError`, `BenchmarkNotFoundError`,
`SuiteValidationError`, unhealthy provider) → `400`/`422` with a `{detail}`
message reusing `format_suite_error` / the exception text.

`GET /api/runs/{run_id}` → run metadata + ordered results:

```json
{
  "run": { "run_id": "a1b2c3", "model": "ollama/llama3.1:8b",
           "benchmark": {"id": "coding-basics-v1", "version": 1},
           "started_at": "…", "finished_at": "…",
           "summary": {"mean_score": 0.82, "pass_rate": 0.75,
                       "p95_latency_ms": 4200} },
  "results": [
    { "task_id": "fizzbuzz", "score": 1.0, "scorer": "unit_test",
      "passed": 3, "total": 3, "latency_ms": 1830,
      "completion_tokens": 96, "prompt": "…", "output": "…",
      "finish_reason": "stop", "error": null }
  ]
}
```

`output` may be large; the list endpoint can return results **without** output
(`load_results(include_output=False)`) and the FE fetches a single task's output
on demand via the `/output` route. (Default: include outputs only on detail.)

### 4.4 Single prompt

| Method | Path | Domain call | Notes |
|---|---|---|---|
| POST | `/api/prompt` | mirror of `cli.prompt` | `{model, text}` → result + run_id |

Quick one-off prompt, persisted as a run like the CLI does. Useful for the
"try a model" affordance without authoring a suite.

### 4.5 Compare & report

| Method | Path | Domain call | Notes |
|---|---|---|---|
| POST | `/api/compare` | `compare_runs` (background) | `{run_ids, mode, judge}` → job → `ComparisonArtifact` |
| GET | `/api/comparisons` | list `~/.elenchos/comparisons/` | saved comparison summaries |
| GET | `/api/comparisons/{id}` | read `comparison.json` | full `ComparisonArtifact` |
| POST | `/api/report` | `build_leaderboard` + `format_report` | `{run_ids, format}` → leaderboard JSON or rendered md/csv |

Compare is judge-driven and can take time → runs as a background job with the
same SSE pattern as runs. `pairwise` requires exactly two runs; `rubric` accepts
two or more (enforced by `compare_runs`; surfaced as `400`).

## 5. Run Execution Model (JobManager + progress)

Runs and compares are **long-running** (seconds to minutes) and the FE needs
live feedback. The BFF owns an in-process **JobManager**:

```python
# src/elenchos/web/jobs.py  (sketch)
@dataclass
class Job:
    job_id: str
    kind: Literal["run", "compare"]
    status: Literal["queued", "running", "done", "error"]
    run_id: str | None = None          # known once the run dir is created
    progress: list[ProgressEvent] = field(default_factory=list)
    result: dict | None = None         # final payload (run detail / artifact)
    error: str | None = None
```

- A `ThreadPoolExecutor` (or one worker thread per job) runs `run_suite` /
  `compare_runs`. The runner is already thread-based and writes results to disk
  per task, so a background thread is a natural fit.
- The BFF calls `run_suite(..., show_progress=False)` to suppress the CLI's
  `console` output, and instead receives progress via a **callback hook**.

**Required small runner change** (backward compatible): add an optional
`on_event` callback to `run_suite` that fires:

- `run_started` — once the run dir exists, carrying `run_id` (so the FE can deep
  link mid-run). Emit right after `create_run`/resume resolution
  (`runner.py:452`).
- `task_done` — per task, carrying `{task_id, index, total, score, error}`
  (the runner already computes this in `_print_task_outcome`).
- `run_finished` — carrying the final `summary`.

The callback defaults to `None`, so the CLI path is unchanged. The JobManager
passes a callback that appends to `job.progress` and notifies SSE subscribers.

If touching the runner is undesirable for v1, a **fallback** needs no code
change: the JobManager tails `results.jsonl` in the run dir and watches
`run.json` for `finished_at` to derive progress. The callback approach is
cleaner and preferred; the tail approach is the zero-touch escape hatch.

**SSE stream** (`GET /api/jobs/{job_id}/events`):

```
event: run_started   data: {"run_id":"a1b2c3"}
event: task_done     data: {"task_id":"fizzbuzz","index":1,"total":5,"score":1.0}
event: task_done     data: {"task_id":"reverse","index":2,"total":5,"score":0.5}
event: run_finished  data: {"summary":{"mean_score":0.75,...}}
```

The FE opens the stream on submit, renders a progress bar + live task list, and
on `run_finished` navigates to the run detail (or refetches it). Polling
`GET /api/jobs/{job_id}` is the fallback if `EventSource` is unavailable.

Job state is **in-memory** (lost on server restart) — acceptable because the
authoritative artifacts are on disk. A restarted server can still show any run
via `/api/runs/{run_id}`; only the live job handle is ephemeral.

## 6. Frontend Structure

### Routes / screens

| Route | Screen | Purpose |
|---|---|---|
| `/` | Dashboard | recent runs, quick links, provider health at a glance |
| `/benchmarks` | Suites list | all templates (built-in/user), searchable |
| `/benchmarks/:id` | Suite detail | tasks, prompts, scorers; **Run** button |
| `/run?benchmark=:id` | Run launcher | pick model/params/toggles → live progress |
| `/runs` | Runs list | history; multi-select for compare |
| `/runs/:runId` | Run detail | per-task prompt/output/score/metrics |
| `/compare` | Compare | pick 2+ runs, mode, judge → result |
| `/comparisons/:id` | Comparison detail | per-task winners / rubric scores |
| `/leaderboard` | Leaderboard | `report` over selected runs |

### State & data

- TanStack Query for all reads (`/benchmarks`, `/runs`, `/providers`, …) with
  sensible cache keys; `/providers` health refetched on focus.
- Mutations: `POST /api/runs`, `POST /api/compare`, `POST /api/prompt`.
- Live progress via a small `useJobStream(jobId)` hook wrapping `EventSource`.

### Component sketch

- `SuiteCard`, `SuiteTaskPanel` (prompt + scorer chips).
- `RunLauncher` (provider select → model select → param fields → exec/judge
  toggles, gated by `requires_code_exec`/`requires_judge`).
- `RunProgress` (progress bar + streaming task rows with score colour).
- `ResultsTable` + `TaskOutputPanel` (collapsible prompt/output, monospace).
- `ScoreBadge` (colour by score, matching the CLI's `_score_style` thresholds).
- `RunPicker` (multi-select used by Compare and Leaderboard).

### Design notes

Match the CLI's information-dense, table-first feel: tables for lists, panels
for prompt/output, colour only to encode score/health/error. Keep chrome
minimal — this is a developer tool, not a marketing site. Reuse the score colour
thresholds already encoded server-side so CLI and UI agree.

## 7. Screen Walkthroughs

**Suite detail → run.** Open `/benchmarks/coding-basics-v1`: header (id,
version, type, description, task count) + one panel per task showing the prompt
and scorer chips. A **Run** button opens the launcher pre-filled with this
suite. If `requires_code_exec`, the launcher shows the code-exec warning and
requires the toggle; if `requires_judge`, it requires a judge model.

**Run launcher → live.** Choose provider (health shown) → model (from
`/providers/{name}/models`) → temperature/max-tokens (defaulted from the suite)
→ concurrency. Submit `POST /api/runs`, open the SSE stream, render progress.
On finish, route to the run detail.

**Runs browser → detail.** `/runs` lists runs (run id, started, benchmark,
model, mean score) newest-first (already sorted by `list_runs`). Selecting two
runs of the same benchmark enables **Compare**. Run detail shows the summary
metrics and a results table; expanding a task reveals prompt + output + score +
latency/tokens, fetching output lazily.

**Compare / leaderboard.** Compare runs a judge job (pairwise/rubric) and shows
per-task winners or rubric scores plus the summary win-rate / mean. Leaderboard
calls `report` and renders the aggregated table (with md/csv/json export).

## 8. Security

- **Bind to `127.0.0.1`** by default; `--host 0.0.0.0` is opt-in and warns.
- **Secrets never leave the server.** Provider API keys are read server-side
  (`config.resolve_provider_endpoint`); no key is ever serialised into a DTO.
- **Code execution stays gated.** The `unit_test` scorer runs untrusted
  model-generated code; the BFF enforces the same `allow_code_exec` gate as the
  CLI — a run with code-exec scorers is rejected (`400`) unless the request sets
  `allow_code_exec: true`. The FE makes this an explicit, warned toggle.
- **CORS**: allowed only for the Vite dev origin in dev; in prod the FE is served
  same-origin so CORS is off.
- **No auth in v1** is acceptable only because it's localhost single-user; this
  is documented and the `0.0.0.0` path warns about the absence of auth.
- Inputs (`model`, `benchmark`, `run_id`) are validated against the registry /
  store before use; path components are never taken raw from the client for
  filesystem access (look up via `find_run`, not string-joined paths).

## 9. Error Handling

- Domain exceptions map to HTTP: `BenchmarkNotFoundError`→404,
  `SuiteValidationError`/`SuiteRunError`/`CompareError`/`ReportError`→400,
  unknown provider→404, unhealthy provider→502, unexpected→500, all with a
  `{detail}` message (reusing `format_suite_error` where it applies).
- Per-task failures inside a run are **not** HTTP errors — they're recorded as
  results with an `error` field (as the runner already does) and rendered inline
  in the results table.
- The FE shows query/mutation error states inline (toast + retry); SSE
  disconnects fall back to polling `GET /api/jobs/{job_id}`.

## 10. Project Structure Additions

```
src/elenchos/
├── cli.py                 # + `serve` command
└── web/
    ├── app.py             # FastAPI app factory, router mounts, static serving
    ├── deps.py            # settings/provider/registry wiring
    ├── jobs.py            # JobManager + ProgressEvent
    ├── schemas.py         # Pydantic DTOs (request/response models)
    ├── routers/
    │   ├── providers.py
    │   ├── benchmarks.py
    │   ├── runs.py        # run, list, detail, output, prompt
    │   ├── jobs.py        # job status + SSE events
    │   └── compare.py     # compare, comparisons, report
    └── static/            # built FE assets (generated; gitignored)

web/                       # FE source (own package.json)
├── index.html
├── vite.config.ts
└── src/
    ├── main.tsx, routes/
    ├── api/               # typed client, generated from OpenAPI (optional)
    ├── hooks/             # useJobStream, queries
    └── components/        # SuiteCard, RunLauncher, ResultsTable, …
```

One **backward-compatible** domain change: an optional `on_event` callback on
`run_suite` (§5). Everything else is pure addition.

## 11. Dev & Build Workflow

- **Dev**: `uvicorn elenchos.web.app:app --reload --port 8765` for the BFF;
  `npm run dev` (Vite, e.g. `:5173`) for the FE, proxying `/api` to the BFF.
- **Prod**: `npm run build` emits to `src/elenchos/web/static/`; `elenchos
  serve` serves those assets + `/api` same-origin. The wheel `force-include`s
  `web/static` (as it already does for `benchmarks/builtin`).
- Tests: BFF endpoints via `fastapi.testclient` over a temp `ELENCHOS_DATA_DIR`,
  reusing the existing storage test fixtures; FE components with Vitest +
  Testing Library (light coverage of the launcher gating and results rendering).

## 12. Phasing

- **Phase 1 (read + run)**: `serve` command, providers/models, benchmarks list &
  detail, runs list & detail (incl. lazy output), run launcher with SSE live
  progress, single prompt. The `on_event` runner hook lands here.
- **Phase 2 (compare)**: compare (pairwise/rubric) as a job, comparisons
  browser, leaderboard/report with export. Dashboard.
- **Phase 3 (polish)**: in-browser suite authoring/validation, run cancellation,
  filtering/search across runs, charts for score/latency trends, persisted job
  history.

## 13. Open Questions

- **Run cancellation**: the current runner has no cancel hook. Add a cooperative
  cancel flag to `run_suite`, or accept that v1 runs are uninterruptible?
- **HTMX vs SPA**: a server-rendered HTMX UI drops the JS build entirely. Worth
  it given the live-progress and multi-select compare interactions? (Default:
  SPA.)
- **Multiple concurrent runs** from the UI: cap them (single worker / queue) to
  avoid overloading a local Ollama/LM Studio, or allow N and let the user
  manage? (Lean: small bounded pool.)
- **Model fan-out**: the CLI roadmap mentions `--model` fan-out; should the
  launcher support running one suite across several models in one action,
  producing a comparable run set?
- **Auth** if `--host 0.0.0.0` is ever needed (shared dev box) — token, or just
  refuse non-localhost binds?
```
