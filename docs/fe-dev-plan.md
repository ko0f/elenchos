# Elenchos — Frontend + BFF Development Plan

Incremental build plan for the web UI (FE) and its backend-for-frontend (BFF),
per [`fe-design.md`](fe-design.md). Like [`dev-plan.md`](dev-plan.md), each phase
is **independently runnable** — at the end of every phase you can open a real
URL (or hit a real endpoint) and observe a real result.

Each phase lists: **Goal**, **What you build**, **How to run/verify it**, and
**Done when**. Phases depend only on earlier ones. The BFF reuses the existing
domain modules in-process — no business logic is re-implemented.

> Prereq: the CLI through `dev-plan.md` Phase 8 (runs, compare, report all work).
> Node 18+ for the FE from Phase 3 on. A live provider (Ollama) to exercise real
> runs. The `web` optional dependency group must be added to `pyproject.toml`
> (`fastapi`, `uvicorn[standard]`, `sse-starlette`) — get sign-off before adding.

---

## Phase 0 — BFF skeleton + `serve` command

**Goal:** an installed `elenchos serve` that boots a FastAPI app and answers a
health check.

**Build**
- Add the `web` optional-dependency group to `pyproject.toml`.
- `web/app.py`: FastAPI app factory; mount an `/api` router; `GET /api/health`
  → `{"status": "ok", "version": <__version__>}`.
- `web/deps.py`: shared `ElenchosSettings` wiring.
- `cli.py`: `serve [--host 127.0.0.1] [--port 8765]` launching uvicorn.

**Run / verify**
```bash
uv sync --all-groups --extra web
uv run elenchos serve            # boots on 127.0.0.1:8765
curl localhost:8765/api/health   # {"status":"ok","version":"0.1.0"}
curl localhost:8765/api/docs     # FastAPI OpenAPI UI loads
```

**Test**
- `fastapi.testclient`: `GET /api/health` → 200 with version.

**Done when:** `elenchos serve` boots and `/api/health` + OpenAPI docs respond.

---

## Phase 1 — Read-only API: providers, benchmarks, runs

**Goal:** every existing read in the CLI is available as JSON over HTTP.

**Build**
- `web/schemas.py`: Pydantic DTOs for provider, suite summary, suite detail
  (with derived `requires_code_exec` / `requires_judge`), run summary, run
  detail + results.
- `web/routers/providers.py`: `GET /api/providers` (`list_provider_names` +
  `health_check` + `base_url`), `GET /api/providers/{name}/models`
  (`list_models`; 404 unknown, 502 unhealthy).
- `web/routers/benchmarks.py`: `GET /api/benchmarks` (`list_suite_summaries`),
  `GET /api/benchmarks/{id}` (`resolve_benchmark`, compute run hints).
- `web/routers/runs.py`: `GET /api/runs` (`list_runs`), `GET /api/runs/{run_id}`
  (`find_run` + `load_results`), `GET /api/runs/{run_id}/results/{task_id}/output`
  (`read_output`, `text/plain`).
- Map domain exceptions → HTTP (`BenchmarkNotFoundError`→404, validation→400).

**Run / verify**
```bash
uv run elenchos serve &
curl localhost:8765/api/providers
curl localhost:8765/api/benchmarks
curl localhost:8765/api/benchmarks/coding-basics-v1   # tasks + requires_code_exec:true
curl localhost:8765/api/runs                          # past runs (created via CLI)
curl localhost:8765/api/runs/<run_id>                 # summary + per-task results
```

**Test**
- TestClient over a temp `ELENCHOS_DATA_DIR` seeded with a known run (reuse
  storage test fixtures): list/detail shapes match; unknown ids → 404.
- Suite detail sets `requires_code_exec`/`requires_judge` correctly.

**Done when:** the whole read surface (providers, suites, runs) is queryable as
JSON and matches what the CLI shows.

---

## Phase 2 — Run execution API: JobManager + SSE progress

**Goal:** start a benchmark run over HTTP and watch it progress live.

**Build**
- `runner.py`: add an optional, backward-compatible `on_event` callback to
  `run_suite` firing `run_started` (carries `run_id`), `task_done`
  (`task_id`/`index`/`total`/`score`/`error`), `run_finished` (`summary`).
  Default `None` → CLI path unchanged.
- `web/jobs.py`: in-memory `JobManager` + `Job`/`ProgressEvent`; a worker thread
  runs `run_suite(..., show_progress=False, on_event=...)`.
- `web/routers/runs.py`: `POST /api/runs` (validate, enqueue job → `{job_id,
  run_id?}`); `POST /api/prompt` (mirror `cli.prompt`).
- `web/routers/jobs.py`: `GET /api/jobs/{job_id}` (poll status),
  `GET /api/jobs/{job_id}/events` (SSE stream of progress).
- Enforce gates server-side: reject code-exec suites without
  `allow_code_exec`; reject judge suites without a judge model (reuse
  `_validate_suite_for_run` semantics → 400).

**Run / verify**
```bash
uv run elenchos serve &
# start a run
curl -X POST localhost:8765/api/runs -H 'content-type: application/json' \
  -d '{"benchmark":"text-reasoning-v1","model":"ollama/llama3.1:8b"}'
# -> {"job_id":"…","run_id":"…"}
curl -N localhost:8765/api/jobs/<job_id>/events   # streams task_done… run_finished
curl localhost:8765/api/runs/<run_id>             # final persisted results
```

**Test**
- `run_suite` with a stub `on_event` and mocked provider emits the three event
  kinds in order; CLI path (no callback) still behaves as before.
- `POST /api/runs` for a `unit_test` suite without `allow_code_exec` → 400.
- Job lifecycle: queued → running → done; final `run_id` resolves to a real run.

**Done when:** a run can be launched and observed to completion entirely over the
API, and the resulting run is identical to a CLI-launched one.

---

## Phase 3 — FE shell + browse benchmarks & runs (read-only)

**Goal:** a working web UI that lists suites and runs and opens their details.

**Build**
- `web/` FE project: Vite + React + TS, React Router, TanStack Query; dev proxy
  `/api` → BFF. Typed API client (optionally generated from OpenAPI).
- Screens: Suites list (`/benchmarks`), Suite detail (`/benchmarks/:id` —
  tasks, prompts, scorer chips), Runs list (`/runs`), Run detail (`/runs/:runId`
  — summary + results table, lazy output fetch).
- Components: `SuiteCard`, `SuiteTaskPanel`, `ResultsTable`, `TaskOutputPanel`,
  `ScoreBadge` (colour thresholds matching the CLI), `ProviderHealth`.

**Run / verify**
```bash
uv run elenchos serve &        # BFF on :8765
cd web && npm install && npm run dev   # Vite on :5173, proxies /api
# open http://localhost:5173
#  -> /benchmarks lists suites; open one, see its tasks
#  -> /runs lists past runs; open one, see per-task output + scores
```

**Test**
- Vitest + Testing Library: Suite detail renders tasks/scorers; Run detail
  renders results and lazy-loads an output panel.

**Done when:** you can browse all benchmark templates and all past results in the
browser, fed by the BFF.

---

## Phase 4 — FE run launcher + live progress

**Goal:** launch a benchmark run from the UI and watch it stream to completion.

**Build**
- `RunLauncher` (`/run?benchmark=:id`): provider select (with health) → model
  select (`/providers/{name}/models`) → temperature/max-tokens (defaulted from
  suite) → concurrency. Code-exec and judge toggles **gated** by the suite's
  `requires_code_exec` / `requires_judge`, with the code-exec warning.
- `useJobStream(jobId)` hook wrapping `EventSource`; polling fallback to
  `GET /api/jobs/{job_id}`.
- `RunProgress`: progress bar + live task rows with score colour; on
  `run_finished`, route to the run detail.
- Wire a **Run** button on Suite detail and a **single-prompt** affordance
  (`POST /api/prompt`).

**Run / verify**
```bash
# (BFF + Vite running as in Phase 3)
# open a suite -> Run -> pick ollama + model -> launch
#  -> progress bar advances per task, scores stream in
#  -> on finish, lands on /runs/<run_id> with full results
```

**Test**
- Launcher disables submit until required gates (code-exec/judge) are satisfied.
- `useJobStream` renders incoming `task_done` events and transitions on
  `run_finished` (mocked EventSource).

**Done when:** a user can pick a model and run any suite from the browser and see
it complete live, with no CLI involved.

---

## Phase 5 — FE compare & leaderboard

**Goal:** compare runs with a judge and view a multi-model leaderboard in the UI.

**Build**
- BFF: `web/routers/compare.py` — `POST /api/compare` (`compare_runs` as a job,
  same SSE pattern), `GET /api/comparisons`, `GET /api/comparisons/{id}`,
  `POST /api/report` (`build_leaderboard` + `format_report`).
- FE: `RunPicker` multi-select on `/runs`; Compare screen (`/compare` — pick
  2+ same-benchmark runs, mode pairwise/rubric, judge model) → per-task winners
  / rubric scores; Comparison detail (`/comparisons/:id`); Leaderboard
  (`/leaderboard`) with md/csv/json export.
- Dashboard (`/`): recent runs, provider health, quick links.

**Run / verify**
```bash
# create two runs of the same suite (UI or CLI), then:
# /runs -> select both -> Compare -> mode pairwise -> judge -> run
#  -> per-task winners + win-rate, saved under ~/.elenchos/comparisons/
# /leaderboard -> select runs -> aggregated table + export
```

**Test**
- BFF: pairwise with !=2 runs → 400; comparisons list/detail round-trip a saved
  artifact; report aggregation matches a fixture.
- FE: Compare enables only for ≥2 same-benchmark runs; leaderboard renders rows.

**Done when:** the full compare + report workflow is usable from the browser and
produces the same artifacts as the CLI.

---

## Phase 6 — Packaging & production serving

**Goal:** `elenchos serve` serves the built UI same-origin from an installed
wheel — no separate dev server.

**Build**
- `npm run build` emits to `src/elenchos/web/static/`; FastAPI serves those
  assets (SPA fallback to `index.html`), `/api` same-origin (CORS off in prod,
  allowed for the Vite origin only in dev).
- `pyproject.toml`: `force-include` `web/static` into the wheel (as
  `benchmarks/builtin` already is). `serve --open` opens the browser.

**Run / verify**
```bash
cd web && npm run build           # -> src/elenchos/web/static/
uv build && uv tool install dist/elenchos-*.whl   # or uv run from a clean env
elenchos serve --open             # UI loads from the install, no Vite
```

**Test**
- Built `index.html` + assets present in the wheel; `GET /` serves the SPA;
  unknown client routes fall back to `index.html`; `/api/*` still JSON.

**Done when:** a fresh install of the wheel runs `elenchos serve` and the full UI
works with no Node/dev server.

---

## Cross-cutting (every phase)

- **BFF stays thin**: routers translate DTOs ↔ domain dataclasses and map
  exceptions to HTTP; all logic stays in the existing `elenchos.*` modules. Only
  sanctioned domain change is the `on_event` hook on `run_suite` (Phase 2).
- **Secrets never cross the wire**: provider API keys stay server-side; no key is
  serialised into a DTO. Bind `127.0.0.1` by default; `--host 0.0.0.0` warns.
- **Code-exec gate enforced server-side** exactly as the CLI does — never trust
  the client to have hidden the toggle.
- **Tests**: BFF via `fastapi.testclient` over a temp `ELENCHOS_DATA_DIR` reusing
  storage fixtures; FE via Vitest + Testing Library. Provider-dependent paths are
  mocked so the suite is green offline.
- **Each phase ends with a runnable demo** (the "Run / verify" block) — the
  acceptance gate before moving on.
- Keep [`fe-design.md`](fe-design.md) in sync if a phase changes an interface.

## Phase summary

| Phase | Deliverable you can run | Needs |
|---|---|---|
| 0 | `elenchos serve` + `/api/health` | `web` deps |
| 1 | read-only JSON API (providers, suites, runs) | existing runs |
| 2 | start a run + SSE progress over HTTP | Ollama |
| 3 | browse suites & runs in the browser | Node |
| 4 | launch a run from the UI, live progress | Ollama |
| 5 | compare + leaderboard in the UI | a judge model |
| 6 | `elenchos serve` serves the built UI from the wheel | Node |
