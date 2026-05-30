# Elenchos — Design Document

A CLI tool for assessing and comparing LLM performance across providers.

## 1. Overview

Elenchos is a command-line Python program that:

1. Connects to any model provider (Ollama, LM Studio, OpenRouter, …).
2. Runs prompts (single or from a benchmark suite) against a chosen model.
3. Persists every run and result to local file storage.
4. Uses a *judge* LLM to compare results across models and score performance.

It supports two task families out of the box — **text** (general reasoning/chat)
and **coding** (code generation, with optional execution-based checks) — and
ships with reusable, pre-planned benchmark suites the user can select and run.

### Goals

- One consistent interface across heterogeneous providers.
- Reproducible runs: every result is saved with the exact inputs and config.
- Pluggable: adding a provider, a benchmark, or a scoring method is a small,
  isolated change.
- Offline-first: works fully against local providers (Ollama, LM Studio); cloud
  (OpenRouter) is opt-in.

### Non-goals (v1)

- Distributed/parallel execution across machines.
- A web UI or hosted service (CLI only; a results export can feed external tools).
- Fine-tuning or training. This tool only *evaluates*.

## 2. Core Concepts

| Concept | Description |
|---|---|
| **Provider** | A backend that hosts models (Ollama, LM Studio, OpenRouter). |
| **Model** | A specific model served by a provider, e.g. `ollama/llama3.1:8b`. |
| **Task** | A single unit of work: a prompt + expectations + scoring config. |
| **Benchmark (Suite)** | A named, versioned collection of tasks (e.g. `coding-basics-v1`). |
| **Run** | One execution of a benchmark against one model, producing per-task results. |
| **Result** | The model output for one task plus computed metrics. |
| **Judge** | An LLM used to score/compare outputs (pairwise or rubric-based). |
| **Report** | An aggregated comparison across runs/models. |

## 3. High-Level Architecture

```
                    ┌────────────────────────────────────────┐
                    │                  CLI                    │
                    │  (argparse/typer commands + output)     │
                    └───────────────────┬────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
        ┌─────▼──────┐          ┌───────▼────────┐        ┌───────▼────────┐
        │  Runner    │          │   Benchmark    │        │   Reporter     │
        │ (orchestr.)│          │    Registry    │        │ (aggregation)  │
        └─────┬──────┘          └───────┬────────┘        └───────┬────────┘
              │                         │                         │
     ┌────────┼─────────┐               │                         │
     │        │         │               │                         │
┌────▼───┐ ┌──▼────┐ ┌──▼─────┐   ┌─────▼──────┐           ┌──────▼──────┐
│Provider│ │Scorer │ │ Judge  │   │ Benchmark  │           │   Storage   │
│ layer  │ │ layer │ │ layer  │   │  loaders   │           │   layer     │
└────┬───┘ └───────┘ └────┬───┘   └────────────┘           └─────────────┘
     │                    │                                       ▲
     │  (uses Provider for judge calls)                           │
     └────────────────────┴───────────────────────────────────────┘
                       all components read/write through Storage
```

### Component responsibilities

- **CLI**: argument parsing, command dispatch, progress/output rendering.
- **Runner**: orchestrates a benchmark run — resolves provider+model, iterates
  tasks, handles concurrency/retries, writes results to storage.
- **Provider layer**: uniform interface over each backend's API.
- **Benchmark Registry + loaders**: discover and load benchmark suites (built-in
  and user-defined).
- **Scorer layer**: deterministic, code-side metrics (exact match, regex,
  unit-test pass rate, latency, token counts).
- **Judge layer**: LLM-based scoring (rubric scoring and pairwise comparison).
- **Storage layer**: read/write runs, results, and reports on local disk.
- **Reporter**: aggregates results into comparison tables / leaderboards.

## 4. Provider Abstraction

All providers implement a single interface. The chat-completions shape is the
common denominator; OpenAI-compatible providers (LM Studio, OpenRouter, and
Ollama's `/v1` endpoint) map directly.

```python
# providers/base.py
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

@dataclass
class Message:
    role: str            # "system" | "user" | "assistant"
    content: str

@dataclass
class GenerationParams:
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    stop: Optional[list[str]] = None

@dataclass
class Completion:
    text: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_ms: float
    raw: dict                      # provider-native response, for debugging
    finish_reason: Optional[str]

class Provider(Protocol):
    name: str

    def list_models(self) -> list[str]: ...

    def complete(
        self,
        model: str,
        messages: list[Message],
        params: GenerationParams,
    ) -> Completion: ...

    def health_check(self) -> bool: ...
```

### Concrete providers (v1)

| Provider | Default endpoint | Auth | Notes |
|---|---|---|---|
| `ollama` | `http://localhost:11434` | none | Native API + OpenAI-compat `/v1`. |
| `lmstudio` | `http://localhost:1234/v1` | none | OpenAI-compatible. |
| `openrouter` | `https://openrouter.ai/api/v1` | API key (env) | OpenAI-compatible; many models. |

Because three of these are OpenAI-compatible, a single `OpenAICompatProvider`
covers LM Studio and OpenRouter (and Ollama's `/v1`), parameterized by base URL
and auth. Ollama may additionally use a native adapter if needed.

API keys are read from environment variables (e.g. `OPENROUTER_API_KEY`), never
stored in config files or results.

### Model identifier format

A fully-qualified model is `<provider>/<model>`, e.g.:

- `ollama/llama3.1:8b`
- `lmstudio/qwen2.5-coder-7b`
- `openrouter/anthropic/claude-sonnet-4-6`

## 5. Benchmark / Task Model

Benchmarks are declarative files (YAML) so users can author them without code.

### Task types

- **`text`** — free-form generation scored by judge rubric and/or string checks.
- **`coding`** — code generation, optionally scored by executing tests.

### Benchmark file schema (YAML)

```yaml
id: coding-basics
version: 1
type: coding                 # "text" | "coding"
description: Basic Python coding tasks with unit tests.
defaults:
  params:
    temperature: 0.0
    max_tokens: 1024
  scoring:
    - type: unit_test         # see Scoring section
tasks:
  - id: fizzbuzz
    prompt: |
      Write a Python function `fizzbuzz(n)` that returns the FizzBuzz
      string for integer n. Respond with code only.
    scoring:
      - type: unit_test
        language: python
        entrypoint: fizzbuzz
        tests: |
          assert fizzbuzz(3) == "Fizz"
          assert fizzbuzz(5) == "Buzz"
          assert fizzbuzz(15) == "FizzBuzz"
          assert fizzbuzz(2) == "2"

  - id: summarize
    type: text                # task can override suite type
    prompt: "Summarize the theory of relativity in two sentences."
    scoring:
      - type: judge_rubric
        rubric: |
          5 = accurate, concise, two sentences.
          1 = inaccurate or off-topic.
```

### Built-in suites (shipped with the tool)

- `text-reasoning-v1` — short reasoning / QA, judge-scored.
- `text-summarization-v1` — summarization quality, judge-scored.
- `coding-basics-v1` — small functions with unit tests.
- `coding-algorithms-v1` — harder algorithmic problems with unit tests.

User suites live under `~/.elenchos/benchmarks/` or a path passed via
`--benchmark-file`; built-ins are packaged with the app. The **Benchmark
Registry** merges both and resolves by `id`.

## 6. Scoring

Two complementary layers.

### 6.1 Deterministic scorers (code-side, cheap, no LLM)

| Scorer | Applies to | Output |
|---|---|---|
| `exact_match` | text | 1.0 / 0.0 vs expected string. |
| `regex_match` | text | 1.0 / 0.0 if pattern found. |
| `contains_all` | text | fraction of required substrings present. |
| `unit_test` | coding | fraction of asserts/tests passing. |
| `metrics` | both | latency, tokens (always recorded). |

`unit_test` extracts the code block from the model output, writes it to a
sandboxed temp module, and runs the provided tests in a **subprocess with a
timeout and resource limits** (see Security). Pass rate = passed / total.

### 6.2 Judge scorers (LLM-based)

The judge is itself a `Provider`+model (configurable, e.g.
`openrouter/anthropic/claude-sonnet-4-6`). Two modes:

- **`judge_rubric`** — judge scores a single output against a rubric, returns a
  numeric score + rationale. Used for absolute scoring.
- **`pairwise`** — judge is shown two models' outputs for the same task and
  picks a winner (or tie). Used for head-to-head comparison and Elo/Bradley–Terry
  ranking across many models.

Judge prompts are templated and request **structured JSON output** so scores
parse reliably:

```json
{ "score": 4, "max": 5, "winner": "A|B|tie", "rationale": "..." }
```

To reduce position bias in pairwise mode, each pair is judged in both orders
(A/B and B/A) and the results averaged.

### Aggregation

Per run, results aggregate to: mean score, pass rate, p50/p95 latency, total
tokens, and (for comparisons) win-rate / rank. The Reporter renders these as a
table and can emit Markdown/CSV/JSON.

## 7. Storage Layout

Plain files under a root dir (default `~/.elenchos/`, override with
`--data-dir` or `ELENCHOS_DATA_DIR`). Human-inspectable, git-friendly, no DB
needed for v1.

```
~/.elenchos/
├── config.yaml                     # default provider endpoints, judge model
├── benchmarks/                     # user-authored suites
│   └── my-suite.yaml
└── runs/
    └── 2026-05-30T14-03-12_coding-basics_ollama_llama3.1-8b_a1b2c3/
        ├── run.json                # run metadata (see below)
        ├── results.jsonl           # one line per task result
        └── outputs/                # raw model outputs per task (optional)
            ├── fizzbuzz.txt
            └── summarize.txt
```

`run.json`:

```json
{
  "run_id": "a1b2c3",
  "started_at": "2026-05-30T14:03:12Z",
  "finished_at": "2026-05-30T14:05:40Z",
  "benchmark": { "id": "coding-basics", "version": 1 },
  "model": "ollama/llama3.1:8b",
  "params": { "temperature": 0.0, "max_tokens": 1024 },
  "tool_version": "0.1.0",
  "summary": { "mean_score": 0.82, "pass_rate": 0.75, "p95_latency_ms": 4200 }
}
```

`results.jsonl` (one object per line):

```json
{"task_id": "fizzbuzz", "score": 1.0, "scorer": "unit_test", "passed": 3, "total": 3, "latency_ms": 1830, "completion_tokens": 96, "output_ref": "outputs/fizzbuzz.txt"}
```

Storing each run in its own timestamped directory makes runs immutable and easy
to compare, archive, or delete. A small index file (or just directory listing)
supports `elenchos list`.

## 8. CLI Surface

Built with `typer` (or `argparse`). Commands:

```
elenchos providers list                       # configured providers + health
elenchos models list --provider ollama        # models available on a provider

elenchos bench list                            # available benchmark suites
elenchos bench show coding-basics              # tasks in a suite

# Run a benchmark against a model
elenchos run \
    --benchmark coding-basics \
    --model ollama/llama3.1:8b \
    [--temperature 0.0] [--max-tokens 1024] [--concurrency 4] [--repeat 1]

# Quick one-off prompt (no suite)
elenchos prompt --model lmstudio/qwen2.5-coder-7b "Write a bubble sort in Go"

# Judge / compare existing runs
elenchos compare <run_id_a> <run_id_b> [<run_id_c> ...] \
    [--judge openrouter/anthropic/claude-sonnet-4-6] [--mode pairwise|rubric]

# Inspect / manage results
elenchos list                                  # past runs
elenchos show <run_id>                         # run detail
elenchos report --runs <id> <id> --format md   # comparison report
elenchos export <run_id> --format csv
```

### Typical workflows

**Single model on a suite**
```
elenchos run --benchmark coding-basics --model ollama/llama3.1:8b
```

**Compare several models** (run each, then compare)
```
elenchos run --benchmark coding-basics --model ollama/llama3.1:8b
elenchos run --benchmark coding-basics --model lmstudio/qwen2.5-coder-7b
elenchos compare <run_a> <run_b> --mode pairwise
```

A convenience flag `--model` accepting multiple values can fan out the run step
across models in one command.

## 9. Execution Flow (a `run`)

1. **Resolve config**: load `config.yaml`, merge CLI overrides.
2. **Resolve provider+model** from `--model`; `health_check()`.
3. **Load benchmark** via registry; validate schema.
4. **Create run dir** and write initial `run.json`.
5. **Iterate tasks** (bounded concurrency via a worker pool):
   - Build messages (system + task prompt).
   - `provider.complete(...)` with retries/backoff on transient errors.
   - Run deterministic scorers immediately.
   - Persist output + result line (streamed to `results.jsonl`).
6. **Judge pass** (if suite uses judge scorers, or deferred to `compare`).
7. **Aggregate** → update `run.json.summary`.
8. **Render** summary table to stdout.

Because results stream to disk per task, an interrupted run is resumable: on
restart, completed `task_id`s in `results.jsonl` are skipped.

## 10. Configuration

`~/.elenchos/config.yaml`:

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
  temperature: 0.0
  max_tokens: 1024
  concurrency: 4
```

Precedence: CLI flags > env vars > `config.yaml` > built-in defaults.

## 11. Security & Sandboxing

The `unit_test` scorer executes **model-generated code**, which is untrusted.

- Run in a **subprocess**, never `exec()` in-process.
- Enforce a wall-clock **timeout** and memory limit (`resource.setrlimit` on
  POSIX) and kill the process group on timeout.
- Run in a temp working directory; no network by default.
- Document the risk; gate execution behind an explicit `--allow-code-exec` flag
  (off by default) or, preferably, run inside a container/`firejail` when
  available.

API keys come only from env vars and are never written to run files or logs.

## 12. Error Handling & Resilience

- **Transient provider errors** (timeouts, 5xx, rate limits): retry with
  exponential backoff (configurable max attempts).
- **Hard failures** (model not found, auth): fail fast with a clear message.
- **Per-task isolation**: one failed task records an `error` result and the run
  continues; it does not abort the whole suite.
- **Partial runs**: always recoverable from `results.jsonl`.

## 13. Project Structure

```
elenchos/
├── pyproject.toml
├── elenchos/
│   ├── cli.py                 # typer app, command wiring
│   ├── config.py              # config loading + precedence
│   ├── runner.py              # orchestration
│   ├── reporter.py            # aggregation + rendering
│   ├── storage.py             # run/result read+write
│   ├── providers/
│   │   ├── base.py            # Provider protocol + dataclasses
│   │   ├── openai_compat.py   # LM Studio, OpenRouter, Ollama /v1
│   │   └── ollama.py          # native adapter (optional)
│   ├── benchmarks/
│   │   ├── registry.py        # discover/load suites
│   │   ├── schema.py          # validation (pydantic)
│   │   └── builtin/*.yaml     # shipped suites
│   ├── scoring/
│   │   ├── deterministic.py   # exact_match, regex, contains_all, metrics
│   │   ├── code_exec.py       # sandboxed unit_test runner
│   │   └── judge.py           # rubric + pairwise judging
│   └── models.py              # core dataclasses (Run, Result, Task, ...)
├── tests/
└── docs/design.md
```

### Key dependencies

- `typer` (CLI), `httpx` (async HTTP to providers), `pydantic` (schema
  validation), `rich` (tables/progress), `pyyaml` (benchmark/config files).

## 14. Extensibility

- **New provider**: implement `Provider`, register it. If OpenAI-compatible, just
  add config — no code.
- **New benchmark**: drop a YAML file in `benchmarks/`.
- **New scorer**: implement a scorer function with a registered `type` name used
  in benchmark YAML.
- **New judge strategy**: add a mode under `scoring/judge.py`.

## 15. Roadmap / Phasing

- **Phase 1 (MVP)**: provider layer (Ollama + LM Studio), `run`, deterministic
  scorers (exact/regex/unit_test + metrics), storage, `list`/`show`, built-in
  `coding-basics` and `text-reasoning` suites.
- **Phase 2**: OpenRouter, judge layer (rubric + pairwise), `compare`/`report`,
  resumable runs, concurrency.
- **Phase 3**: richer reports (Elo ranking, charts/HTML export), more built-in
  suites, container-based code sandboxing, `--model` fan-out.

## 16. Open Questions

- Code-exec languages beyond Python in v1? (Start Python-only.)
- Judge cost controls — cap number of pairwise comparisons for large model sets
  (e.g. sample, or use Swiss-style pairing instead of all-pairs)?
- Do we need streaming output, or is single-shot completion enough for scoring?
  (Single-shot is sufficient for v1.)
```
