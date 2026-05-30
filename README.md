# lmbench

Python skeleton for benchmarking local LLMs via [LM Studio](https://lmstudio.ai/).

## Setup

```bash
uv sync --all-groups
cp .env.example .env
```

Start LM Studio local server on port `1234` with a model loaded.

## Run

```bash
uv run lmbench run --prompts prompts/sample.jsonl
```

Results write to `results/` as timestamped JSON.

## Dev

```bash
uv run pytest
```

## Layout

```
src/lmbench/     package (client, runner, metrics)
prompts/         benchmark prompt sets (JSONL)
results/         run outputs (gitignored)
tests/           unit tests
docs/            LM Studio API notes
```
