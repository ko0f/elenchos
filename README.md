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
| `elenchos serve` | Start the web UI backend (requires `web` extra) |

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

Elenchos includes a local web UI backed by a FastAPI **BFF** (backend-for-frontend)
in `src/elenchos/web/`. The UI and the CLI share the same data directory
(`~/.elenchos/`).

| Mode | Status | How to run |
|---|---|---|
| BFF (JSON API) | **Available** | `elenchos serve` |
| Frontend dev server (Vite) | Planned — [`docs/fe-dev-plan.md`](docs/fe-dev-plan.md) Phase 3 | BFF + `npm run dev` in `web/` |
| Production (built UI from wheel) | Planned — Phase 6 | `elenchos serve --open` |

Design: [`docs/fe-design.md`](docs/fe-design.md) · build plan:
[`docs/fe-dev-plan.md`](docs/fe-dev-plan.md).

### Prerequisites

- Python 3.11+ with the `web` optional dependency group
- **Node 18+** — required once the `web/` frontend project lands (Phase 3); not
  needed for the BFF-only workflow below

### Backend (BFF)

Install web dependencies and start the server (defaults to `127.0.0.1:8765`):

```bash
uv sync --all-groups --extra web
uv run elenchos serve
```

Options: `--host` (default `127.0.0.1`), `--port` (default `8765`). Binding to a
non-localhost address prints a warning — provider API keys and run data stay
server-side, but the API is exposed on your network.

**Verify the BFF** (no browser required):

```bash
curl localhost:8765/api/health
curl localhost:8765/api/benchmarks
curl localhost:8765/api/runs
```

Open **OpenAPI docs** at [http://localhost:8765/api/docs](http://localhost:8765/api/docs).

Read-only endpoints available today:

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check + version |
| GET | `/api/providers` | Provider names, endpoints, health |
| GET | `/api/providers/{name}/models` | Models on a provider |
| GET | `/api/benchmarks` | List benchmark suites |
| GET | `/api/benchmarks/{id}` | Suite detail (tasks, scorers, run hints) |
| GET | `/api/runs` | List persisted runs |
| GET | `/api/runs/{run_id}` | Run detail + per-task results |
| GET | `/api/runs/{run_id}/results/{task_id}/output` | Raw task output (`text/plain`) |

Create runs via the CLI first (`elenchos run …`); the UI will list them once the
frontend is wired up.

### Frontend development (planned)

When the `web/` Vite + React project is added (Phase 3), run **two processes** —
BFF and Vite dev server — in separate terminals:

**Terminal 1 — BFF**

```bash
uv sync --all-groups --extra web
uv run elenchos serve          # http://localhost:8765
```

**Terminal 2 — frontend**

```bash
cd web
npm install
npm run dev                    # http://localhost:5173, proxies /api → :8765
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to the
BFF so the browser stays same-origin for API calls during development.

Run frontend tests with `npm test` (Vitest) from `web/`.

### Production serving (planned)

After Phase 6, a built install serves the UI and API from one process — no Node
dev server:

```bash
cd web && npm run build        # emits to src/elenchos/web/static/
uv build && uv tool install dist/elenchos-*.whl
elenchos serve --open          # UI + /api on http://127.0.0.1:8765
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
src/elenchos/web/       BFF (FastAPI) — JSON API for the web UI
src/elenchos/benchmarks/builtin/   Built-in benchmark suites (.yaml)
web/                    Frontend source (Vite + React — planned, Phase 3)
prompts/                Legacy sample prompts (JSONL)
tests/                  Unit tests
docs/                   Design docs and provider notes
~/.elenchos/runs/       Persisted run data (created at runtime)
```
