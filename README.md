# elenchos

CLI for assessing and comparing LLM performance — named for the Socratic *elenchus*
(cross-examination through dialogue).

Connect to local or remote model providers (Ollama, LM Studio, OpenRouter), run
benchmark suites, persist results, and compare models with a judge LLM.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A running model provider (e.g. Ollama on `localhost:11434`, or LM Studio on
  `localhost:1234`)
- **Node 18+** — only for web frontend development/build (`web/`); not required
  for CLI-only use

## Setup

```bash
uv sync --all-groups
cp .env.example .env   # optional — override provider URLs and API keys
```

Run commands with `uv run elenchos …` from the repo root, or install the package
into your environment with `uv sync` and call `elenchos` directly.

## Configuration

Provider endpoints resolve in this order: **CLI flags → environment variables →
`~/.elenchos/config.yaml` → built-in defaults**.

### Environment variables

Set in `.env` or your shell (prefix `ELENCHOS_`):

| Variable | Purpose |
|---|---|
| `ELENCHOS_OLLAMA_BASE_URL` | Ollama OpenAI-compatible endpoint (default `http://localhost:11434`) |
| `ELENCHOS_OLLAMA_API_KEY` | Optional API key for Ollama |
| `ELENCHOS_LMSTUDIO_BASE_URL` | LM Studio endpoint (default `http://localhost:1234/v1`) |
| `ELENCHOS_LMSTUDIO_API_KEY` | Optional API key for LM Studio |
| `ELENCHOS_OPENROUTER_BASE_URL` | OpenRouter endpoint |
| `ELENCHOS_OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_API_KEY` | Also accepted for OpenRouter when not using `ELENCHOS_` prefix |

Run data and optional config live under `~/.elenchos/` by default (`ELENCHOS_DATA_DIR`
to override).

### Config file (optional)

Create `~/.elenchos/config.yaml` for persistent defaults:

```yaml
providers:
  ollama:
    base_url: http://localhost:11434
  lmstudio:
    base_url: http://localhost:1234/v1
  openrouter:
    base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

judge:
  model: openrouter/anthropic/claude-sonnet-4-6
  mode: pairwise

defaults:
  concurrency: 4
```

## Quick start

1. **Check providers** — confirm your backend is reachable:

   ```bash
   uv run elenchos providers list
   ```

2. **List models** on a provider:

   ```bash
   uv run elenchos models list --provider ollama
   ```

3. **List benchmark suites**:

   ```bash
   uv run elenchos bench list
   ```

   Built-in suites: `text-reasoning-v1`, `coding-basics-v1`.

4. **Run a benchmark** — model id is `provider/model-name`:

   ```bash
   uv run elenchos run \
     --benchmark text-reasoning-v1 \
     --model ollama/llama3.1:8b
   ```

5. **Inspect runs**:

   ```bash
   uv run elenchos list
   uv run elenchos show <run-id>
   ```

6. **Or use the web UI** — see [Web UI](#web-ui) (`elenchos serve` + browser).

## Commands

Global option: `-v` / `--verbose` for debug logging on stderr.

| Command | Description |
|---|---|
| `elenchos version` | Print installed version |
| `elenchos providers list` | List providers and health status |
| `elenchos models list --provider <name>` | List models on a provider |
| `elenchos bench list` | List benchmark suites |
| `elenchos bench show <suite-id>` | Show tasks in a suite |
| `elenchos prompt "<text>" --model <provider/model>` | Send one prompt; save run |
| `elenchos run --benchmark <id> --model <provider/model>` | Run a full benchmark suite |
| `elenchos list` | List persisted runs |
| `elenchos show <run-id>` | Show run details and outputs |
| `elenchos compare <run-id> …` | Compare runs with a judge LLM |
| `elenchos report --runs <id> …` | Build a leaderboard (`--format md\|csv\|json`) |
| `elenchos serve [--open]` | Start web UI + BFF (requires `web` extra) |

### `run` options

```bash
uv run elenchos run \
  --benchmark text-reasoning-v1 \
  --model ollama/llama3.1:8b \
  --temperature 0.0 \
  --max-tokens 512 \
  --concurrency 4 \
  --judge ollama/llama3.1:8b \
  --allow-code-exec          # required for coding suites with unit_test scorer
```

Use `--benchmark-file path/to/suite.yaml` to load a custom suite instead of a
built-in id.

### Compare and report

After running the same benchmark against multiple models:

```bash
uv run elenchos compare run-a run-b --judge ollama/llama3.1:8b
uv run elenchos report --runs run-a run-b run-c --format md
```

Set `judge.model` in `~/.elenchos/config.yaml` to avoid passing `--judge` every
time.

## Web UI

Local web UI for browsing benchmark suites, launching runs with live progress,
inspecting results, comparing runs with a judge, and building leaderboards. A
FastAPI **BFF** in `src/elenchos/web/` wraps the same Python domain code as the
CLI; the React frontend lives in `web/`. Both read and write `~/.elenchos/`.

Design: [`docs/fe-design.md`](docs/fe-design.md) · build plan:
[`docs/fe-dev-plan.md`](docs/fe-dev-plan.md).

### Prerequisites

- Python 3.11+ with the `web` optional dependency group
- **Node 18+** — for frontend development and building static assets (`web/`)
- A running model provider (same as CLI)

Install Python web deps once:

```bash
uv sync --all-groups --extra web
```

### Screens

| Route | Purpose |
|---|---|
| `/` | Dashboard — recent runs, comparisons, quick links |
| `/benchmarks` | List suites (built-in + user) |
| `/benchmarks/:id` | Suite detail — tasks, prompts, scorers; **Run** button |
| `/run?benchmark=:id` | Run launcher — model, params, code-exec/judge gates, live progress |
| `/prompt` | Quick one-off prompt (saved as a run) |
| `/runs` | Run history; multi-select to compare |
| `/runs/:runId` | Run detail — scores, metrics; expand task for prompt/output |
| `/compare?runs=a,b,…` | Judge comparison (pairwise or rubric) |
| `/comparisons/:id` | Saved comparison detail |
| `/leaderboard` | Aggregate scores across runs; export md/csv/json |

Task output is loaded on demand from `/api/runs/{run_id}/results/{task_id}/output`
when you expand a row (run detail omits large outputs from the JSON payload).

### Development (BFF + Vite)

Run **two processes** in separate terminals:

**Terminal 1 — BFF**

```bash
uv run elenchos serve          # http://127.0.0.1:8765
```

**Terminal 2 — frontend**

```bash
cd web
npm install
npm run dev                    # http://localhost:5173, proxies /api → :8765
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to the
BFF; CORS is enabled for the dev origin automatically when no built UI is present.

### Production (single process)

Build the frontend into the Python package, then serve UI and API from one origin:

```bash
cd web && npm run build        # → src/elenchos/web/static/
uv run elenchos serve --open   # http://127.0.0.1:8765
```

For an installed wheel: `uv build && uv tool install dist/elenchos-*.whl`, then
`elenchos serve --open`. No Node dev server required at runtime.

### `serve` options

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Listen port |
| `--open` | off | Open the UI in a browser |

Binding to a non-localhost address prints a warning — provider API keys and run
data stay server-side, but the API is exposed on your network with no auth.

### HTTP API

Full schema: [http://localhost:8765/api/docs](http://localhost:8765/api/docs) (when
`elenchos serve` is running).

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check + version |
| GET | `/api/providers` | Provider names, endpoints, health |
| GET | `/api/providers/{name}/models` | Models on a provider |
| GET | `/api/benchmarks` | List benchmark suites |
| GET | `/api/benchmarks/{id}` | Suite detail (`requires_code_exec`, `requires_judge`) |
| GET | `/api/runs` | List persisted runs |
| GET | `/api/runs/{run_id}` | Run metadata + per-task results (no inline output) |
| GET | `/api/runs/{run_id}/results/{task_id}/output` | Raw task output (`text/plain`) |
| POST | `/api/runs` | Start a benchmark run → `{job_id}`; live progress via jobs |
| POST | `/api/prompt` | One-off prompt → result + `run_id` |
| GET | `/api/jobs/{job_id}` | Poll job status (SSE fallback) |
| GET | `/api/jobs/{job_id}/events` | SSE stream (`run_started`, `task_done`, `run_finished`, `job_error`, …) |
| POST | `/api/compare` | Start judge comparison → `{job_id}` |
| GET | `/api/comparisons` | List saved comparisons |
| GET | `/api/comparisons/{id}` | Comparison detail |
| POST | `/api/report` | Leaderboard (`format`: `json`, `md`, or `csv`) |

Quick smoke test (no browser):

```bash
curl localhost:8765/api/health
curl localhost:8765/api/benchmarks
curl localhost:8765/api/runs
```

Example — start a run and watch progress:

```bash
curl -X POST localhost:8765/api/runs -H 'content-type: application/json' \
  -d '{"benchmark":"text-reasoning-v1","model":"ollama/llama3.1:8b"}'
# → {"job_id":"…","run_id":null}
curl -N localhost:8765/api/jobs/<job_id>/events
```

Coding suites with `unit_test` scorers require `"allow_code_exec": true` in the
POST body (same gate as CLI `--allow-code-exec`).

### Tests

```bash
uv run pytest tests/test_web_api.py tests/test_web_static.py tests/test_web_health.py
cd web && npm test
```

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
```

Design and architecture: [`docs/design.md`](docs/design.md). Web UI:
[`docs/fe-design.md`](docs/fe-design.md).

## Layout

```
src/elenchos/           Python package (CLI, providers, runner, scoring)
src/elenchos/web/       BFF (FastAPI) + built static UI (`web/static/`)
src/elenchos/benchmarks/builtin/   Built-in benchmark suites (.yaml)
web/                    Frontend source (Vite + React + TypeScript)
prompts/                Legacy sample prompts (JSONL)
tests/                  Unit tests
docs/                   Design docs and provider notes
~/.elenchos/runs/       Persisted run data (created at runtime)
```
