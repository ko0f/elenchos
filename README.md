# elenchos

CLI for assessing and comparing LLM performance — named for the Socratic *elenchus*
(cross-examination through dialogue).

## Setup

```bash
uv sync --all-groups
cp .env.example .env
```

Start LM Studio local server on port `1234` with a model loaded.

## Run

```bash
uv run elenchos run --prompts prompts/sample.jsonl
```

Results write to `results/` as timestamped JSON.

## Dev

```bash
uv run pytest
```

## Layout

```
src/elenchos/    package (client, runner, metrics)
prompts/         benchmark prompt sets (JSONL)
results/         run outputs (gitignored)
tests/           unit tests
docs/            design + LM Studio API notes
```
