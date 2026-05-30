# Elenchos — Development Plan

Incremental build plan. Each phase is **independently runnable** — at the end of
every phase you can execute a real command and observe a real result, so progress
is always verifiable, not just "code exists".

Each phase lists: **Goal**, **What you build**, **How to run/verify it**, and
**Done when**. Phases depend only on earlier ones.

> Prereq: Python 3.11+, [uv](https://docs.astral.sh/uv/), an Ollama instance running locally (`ollama serve` with
> at least one model pulled, e.g. `ollama pull llama3.1:8b`). LM Studio and an
> OpenRouter key are needed only from Phase 6 onward.

---

## Phase 0 — Project skeleton

**Goal:** an installed CLI that runs and prints its version.

**Build**
- `pyproject.toml` (package `elenchos`, console script `elenchos`).
- `elenchos/cli.py` with a `typer` app and a `version` command.
- `elenchos/console.py`: shared `rich.console.Console` and `logging` setup via
  `RichHandler` (colored, structured stderr logs; stdout reserved for command
  output).
- Dev tooling: `pytest`, `ruff`, `rich`. Empty `tests/` with one smoke test.

**Run / verify**
```bash
uv sync --all-groups
uv run elenchos version   # prints 0.1.0
uv run pytest             # 1 passing smoke test
```

**Done when:** `uv run elenchos version` works after `uv sync` and CI/pytest is green.

---

## Phase 1 — Provider layer + `prompt` (single call to a real model)

**Goal:** send one prompt to a real local model and see the response.

**Build**
- `providers/base.py`: `Message`, `GenerationParams`, `Completion`, `Provider`
  protocol.
- `providers/openai_compat.py`: `OpenAICompatProvider` (httpx) targeting Ollama's
  `/v1` endpoint.
- `models.py`: parse `provider/model` identifiers.
- `cli.py`: `prompt --model <id> "text"` and `providers list` (with
  `health_check`). Use `rich` for response text and status (green healthy, red
  unhealthy); log request/response details at DEBUG via `RichHandler`.

**Run / verify**
```bash
elenchos providers list                       # colored status: ollama healthy
elenchos prompt --model ollama/llama3.1:8b "Say hello in one word."
# -> colored model output + latency + token counts
```

**Test**
- Unit: model-id parsing, message building.
- Integration (skipped if no Ollama): one real `complete()` call returns
  non-empty text.

**Done when:** a real prompt round-trips against local Ollama and prints output +
metrics.

---

## Phase 2 — Storage + `list`/`show`

**Goal:** every model call is persisted and inspectable later.

**Build**
- `storage.py`: create timestamped run dirs, write `run.json`, append
  `results.jsonl`, save raw outputs; read back for listing/detail.
- `models.py`: `Run`, `Result` dataclasses.
- Make `prompt` persist its call as a single-task run.
- `cli.py`: `list`, `show <run_id>`. Render run lists and detail views with
  `rich` tables/panels.

**Run / verify**
```bash
elenchos prompt --model ollama/llama3.1:8b "2+2?"
elenchos list                  # shows the run just created
elenchos show <run_id>         # shows prompt, output, latency, tokens
ls ~/.elenchos/runs/           # files exist on disk
```

**Test**
- Round-trip: write a run, read it back, fields match.
- `list` reflects newly created runs; `show` renders a known run.

**Done when:** runs survive across invocations and are listed/shown from disk.

---

## Phase 3 — Benchmark loading + `bench list/show`

**Goal:** load declarative YAML suites and inspect their tasks (no execution yet).

**Build**
- `benchmarks/schema.py`: pydantic models for suite/task; validation with clear
  errors.
- `benchmarks/registry.py`: discover built-in + user suites, resolve by `id`.
- One built-in suite `text-reasoning-v1.yaml` (a few text tasks).
- `cli.py`: `bench list`, `bench show <id>`, plus `--benchmark-file <path>`.

**Run / verify**
```bash
elenchos bench list                    # lists text-reasoning-v1
elenchos bench show text-reasoning-v1  # prints its tasks
# malformed YAML:
elenchos bench show ./broken.yaml      # clear validation error, non-zero exit
```

**Test**
- Valid suite loads; invalid suite raises a readable validation error.
- Registry merges built-in + user dirs; id resolution works.

**Done when:** suites load and validate; tasks are viewable from the CLI.

---

## Phase 4 — `run` + deterministic scoring (text)

**Goal:** run a full text suite against a model end-to-end with code-side scoring.

**Build**
- `scoring/deterministic.py`: `exact_match`, `regex_match`, `contains_all`,
  always-on `metrics` (latency, tokens).
- `runner.py`: load suite → iterate tasks → `complete()` → score → stream
  results → aggregate `summary`. Sequential for now. Per-task progress via
  `rich` progress/spinner; errors in red.
- `reporter.py`: render a per-run summary table (`rich`); color pass/fail and
  latency columns.
- `cli.py`: `run --benchmark <id> --model <id>`.

**Run / verify**
```bash
elenchos run --benchmark text-reasoning-v1 --model ollama/llama3.1:8b
# -> per-task scores + summary table (mean score, pass rate, p95 latency)
elenchos show <run_id>     # persisted results match what was printed
```

**Test**
- Each deterministic scorer: known input → expected score.
- Runner on a tiny fixture suite (mocked provider) produces expected summary.

**Done when:** a real suite runs against a real model and produces scored,
persisted, viewable results.

---

## Phase 5 — Coding tasks + sandboxed `unit_test` scorer

**Goal:** evaluate code-generation tasks by executing model code against tests.

**Build**
- `scoring/code_exec.py`: extract code block → write temp module → run tests in a
  **subprocess** with timeout + `resource` limits + temp cwd; pass rate =
  passed/total. Kill process group on timeout.
- Built-in suite `coding-basics-v1.yaml` (e.g. fizzbuzz, factorial) with
  `unit_test` scoring.
- `--allow-code-exec` flag (off by default); refuse to run `unit_test` without it.

**Run / verify**
```bash
elenchos run --benchmark coding-basics-v1 \
    --model ollama/llama3.1:8b --allow-code-exec
# -> pass rates per task; failing/timeout code scored 0, run continues
elenchos run --benchmark coding-basics-v1 --model ollama/...   # no flag -> refuses
```

**Test**
- Known-good code → pass; broken code → fail; infinite loop → timeout, not hang.
- Sandbox: no flag → execution refused.

**Done when:** coding suites run safely; malicious/slow code can't hang or harm
the host, and results are scored.

---

## Phase 6 — More providers (LM Studio, OpenRouter)

**Goal:** the same commands work against LM Studio and OpenRouter.

**Build**
- Config-driven provider registration in `config.py` (base URLs, `api_key_env`).
- `config.yaml` loading with precedence (CLI > env > file > defaults).
- Verify `OpenAICompatProvider` works for LM Studio and OpenRouter unchanged;
  OpenRouter key from env only.

**Run / verify**
```bash
elenchos models list --provider lmstudio
elenchos run --benchmark text-reasoning-v1 --model lmstudio/<model>
export OPENROUTER_API_KEY=...
elenchos run --benchmark text-reasoning-v1 --model openrouter/<vendor>/<model>
```

**Test**
- Config precedence resolves correctly.
- Provider factory builds the right client per id (mocked HTTP).

**Done when:** all three providers run the same suite with no code changes beyond
config.

---

## Phase 7 — Judge layer + `compare`

**Goal:** use a judge LLM to score/compare runs across models.

**Build**
- `scoring/judge.py`: `judge_rubric` (absolute score + rationale) and `pairwise`
  (A/B winner, judged in both orders to cancel position bias). Structured JSON
  output, parsed defensively.
- Judge is a configurable `Provider`+model (from `config.yaml`).
- `cli.py`: `compare <run_a> <run_b> [...] [--mode pairwise|rubric] [--judge id]`.
- Wire `judge_rubric` scorer into `run` for text suites that request it.

**Run / verify**
```bash
# produce two runs first
elenchos run --benchmark text-reasoning-v1 --model ollama/llama3.1:8b
elenchos run --benchmark text-reasoning-v1 --model lmstudio/<model>
elenchos compare <run_a> <run_b> --mode pairwise
# -> per-task winners + overall win-rate, written as a comparison artifact
```

**Test**
- Judge JSON parsing (including malformed output handling) with a mocked judge.
- Pairwise both-orders averaging; rubric score extraction.

**Done when:** two real runs can be compared and a winner/scoreboard is produced.

---

## Phase 8 — Reporting, concurrency, resumability

**Goal:** production niceties that make larger comparisons practical.

**Build**
- `reporter.py`: `report --runs ... --format md|csv|json`; multi-model leaderboard
  (mean score, pass rate, win-rate/rank).
- Bounded-concurrency worker pool in `runner.py` (`--concurrency`).
- Resumable runs: skip `task_id`s already present in `results.jsonl`.
- Retries with exponential backoff on transient provider errors.

**Run / verify**
```bash
elenchos run --benchmark coding-basics-v1 --model ollama/... --concurrency 4
# interrupt mid-run (Ctrl-C), rerun same command -> resumes, skips completed tasks
elenchos report --runs <a> <b> <c> --format md   # leaderboard table
```

**Test**
- Resume: pre-seed partial `results.jsonl`, run, only missing tasks execute.
- Retry: provider failing N-1 times then succeeding is retried, not failed.
- Report aggregation matches hand-computed values on a fixture.

**Done when:** large multi-model runs are fast, interrupt-safe, and produce a
shareable report.

---

## Cross-cutting (every phase)

- **Terminal output via `rich`**: shared `Console` from `elenchos/console.py`.
  User-facing results (tables, panels, metrics) on stdout; operational logs on
  stderr through `logging` + `RichHandler` with level-based color. No raw
  `print()` in library code.
- **Tests run via `uv run pytest`**; integration tests that need a live provider are
  marked and skipped when unavailable, so the suite is always green offline.
- **Each phase ends with a runnable demo command** (the "Run / verify" block) —
  this is the acceptance gate before moving on.
- Keep `docs/design.md` in sync if a phase changes an interface.

## Phase summary

| Phase | Deliverable you can run | Needs |
|---|---|---|
| 0 | `elenchos version` | — |
| 1 | `prompt` against Ollama | Ollama |
| 2 | `list` / `show` persisted runs | Ollama |
| 3 | `bench list/show` | — |
| 4 | `run` text suite + scores | Ollama |
| 5 | `run` coding suite (sandboxed) | Ollama |
| 6 | same runs on LM Studio / OpenRouter | LM Studio / OR key |
| 7 | `compare` via judge LLM | a judge model |
| 8 | `report`, concurrency, resume | — |
